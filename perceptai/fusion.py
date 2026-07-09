"""Perception fusion: many observations in, one element out.

When multiple providers observe the same element (UIA sees a button,
OCR reads its label, vision describes it), fusion merges them into a
single UIElement with:
- role/name/bbox taken from the most trusted source that knows them,
- confidence combined noisy-OR style (corroboration raises certainty,
  it never fabricates it — capped below 1.0),
- every contributing source recorded, so uncertainty stays visible all
  the way to the planner and the report.

Pure logic, no I/O, deterministic — fully unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .config import EngineConfig
from .contracts import (
    INTERACTIVE_ROLES,
    BoundingBox,
    Observation,
    UIElement,
)

_WS = re.compile(r"\s+")

# Confidence is never reported as absolute certainty.
_CONFIDENCE_CAP = 0.99


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text).strip().casefold()


def text_similarity(a: str, b: str) -> float:
    """Similarity in [0, 1]: exact > containment > fuzzy ratio."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        shorter, longer = sorted((len(na), len(nb)))
        return max(0.85, shorter / longer)
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class _Cluster:
    members: list[tuple[Observation, float]] = field(default_factory=list)  # (obs, weight)

    def add(self, obs: Observation, weight: float) -> None:
        self.members.append((obs, weight))

    @property
    def best(self) -> tuple[Observation, float]:
        return max(self.members, key=lambda m: m[1])

    @property
    def bbox(self) -> BoundingBox | None:
        for obs, _w in sorted(self.members, key=lambda m: -m[1]):
            if obs.bbox is not None and obs.bbox.valid:
                return obs.bbox
        for obs, _w in sorted(self.members, key=lambda m: -m[1]):
            if obs.bbox is not None:
                return obs.bbox
        return None

    @property
    def texts(self) -> list[str]:
        return [obs.text for obs, _w in self.members if obs.text]


class FusionEngine:
    def __init__(self, config: EngineConfig):
        self._config = config

    def trust(self, source: str) -> float:
        return float(self._config.source_trust.get(str(source), 0.5))

    def weight(self, obs: Observation) -> float:
        native = max(0.0, min(1.0, float(obs.confidence)))
        return native * self.trust(obs.source.value if hasattr(obs.source, "value") else obs.source)

    # ------------------------------------------------------------- fusing

    def fuse(self, observations: list[Observation]) -> list[UIElement]:
        positioned = [o for o in observations if o.bbox is not None]
        unpositioned = [o for o in observations if o.bbox is None]

        clusters: list[_Cluster] = []
        # Most trusted observations seed clusters; weaker ones join them.
        for obs in sorted(positioned, key=lambda o: -self.weight(o)):
            target = self._matching_cluster(clusters, obs)
            if target is None:
                target = _Cluster()
                clusters.append(target)
            target.add(obs, self.weight(obs))

        # Position-less observations (vision) anchor to clusters by text.
        for obs in sorted(unpositioned, key=lambda o: -self.weight(o)):
            target = self._best_text_cluster(clusters, obs)
            if target is None:
                target = _Cluster()
                clusters.append(target)
            target.add(obs, self.weight(obs))

        elements = [self._to_element(cluster) for cluster in clusters]
        elements = self._trim(elements)
        elements.sort(key=_element_order)
        for i, el in enumerate(elements, start=1):
            el.id = f"el_{i:03d}"
        return elements

    def _matching_cluster(self, clusters: list[_Cluster], obs: Observation) -> _Cluster | None:
        assert obs.bbox is not None
        best: tuple[float, _Cluster] | None = None
        for cluster in clusters:
            cbox = cluster.bbox
            if cbox is None:
                continue
            score = self._spatial_match(cbox, obs, cluster)
            if score > 0 and (best is None or score > best[0]):
                best = (score, cluster)
        return best[1] if best else None

    def _spatial_match(self, cbox: BoundingBox, obs: Observation, cluster: _Cluster) -> float:
        """> 0 when obs and cluster are the same element. Overlap alone is
        enough when strong; containment needs textual agreement so a text
        line inside a large pane doesn't get swallowed by it."""
        assert obs.bbox is not None
        iou = cbox.iou(obs.bbox)
        if iou >= self._config.fusion_iou_threshold:
            return 1.0 + iou
        contained = (
            cbox.contains(*obs.bbox.center) or obs.bbox.contains(*cbox.center)
        )
        if contained and self._texts_agree(cluster, obs):
            return 1.0
        return 0.0

    def _best_text_cluster(self, clusters: list[_Cluster], obs: Observation) -> _Cluster | None:
        if not obs.text:
            return None
        best: tuple[float, _Cluster] | None = None
        for cluster in clusters:
            score = max(
                (text_similarity(obs.text, t) for t in cluster.texts), default=0.0
            )
            if score >= self._config.fusion_text_similarity and (
                best is None or score > best[0]
            ):
                best = (score, cluster)
        return best[1] if best else None

    def _texts_agree(self, cluster: _Cluster, obs: Observation) -> bool:
        if not obs.text:
            return False
        return any(
            text_similarity(obs.text, t) >= self._config.fusion_text_similarity
            for t in cluster.texts
        )

    # ----------------------------------------------------------- assembly

    def _to_element(self, cluster: _Cluster) -> UIElement:
        ranked = sorted(cluster.members, key=lambda m: -m[1])

        # Noisy-OR: independent agreeing sources compound certainty.
        disbelief = 1.0
        for _obs, weight in ranked:
            disbelief *= 1.0 - max(0.0, min(1.0, weight))
        confidence = min(_CONFIDENCE_CAP, round(1.0 - disbelief, 3))

        role = next(
            (o.role for o, _w in ranked if o.role not in ("", "text", "unknown")),
            ranked[0][0].role or "text",
        )
        name = next((o.text for o, _w in ranked if o.text.strip()), "")
        window = next((o.window for o, _w in ranked if o.window), "")

        attributes: dict = {}
        for obs, _w in reversed(ranked):  # highest trust writes last, wins
            attributes.update(obs.attributes)

        sources: list[str] = []
        for obs, _w in ranked:
            value = obs.source.value if hasattr(obs.source, "value") else str(obs.source)
            if value not in sources:
                sources.append(value)

        interactive = role in INTERACTIVE_ROLES or bool(attributes.get("clickable"))
        # `secure` is OR-ed across sources — a password field is secure even if
        # only one source (DOM type=password / UIA IsPassword) detected it, and
        # a source that missed it must never downgrade it.
        secure = any(bool(o.attributes.get("secure")) for o, _w in ranked)
        return UIElement(
            id="",  # assigned after final ordering
            role=role,
            name=name,
            bbox=cluster.bbox,
            confidence=confidence,
            sources=sources,
            interactive=interactive,
            enabled=bool(attributes.get("enabled", True)),
            focused=bool(attributes.get("focused", False)),
            secure=secure,
            value=str(attributes.get("value", "")),
            window=window,
            attributes=attributes,
        )

    def _trim(self, elements: list[UIElement]) -> list[UIElement]:
        limit = self._config.world_max_elements
        if len(elements) <= limit:
            return elements
        # Interactive and high-confidence elements survive; decorative
        # low-confidence text is dropped first.
        ranked = sorted(elements, key=lambda e: (e.interactive, e.confidence), reverse=True)
        return ranked[:limit]


def _element_order(el: UIElement) -> tuple:
    if el.bbox is not None:
        return (el.window, 0, el.bbox.top, el.bbox.left, el.name)
    return (el.window, 1, 0, 0, el.name)
