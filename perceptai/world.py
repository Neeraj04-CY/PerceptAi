"""The world model — the ONE perception surface the runtime consumes.

WorldModel orchestrates perception providers under budgets, fuses their
observations into a WorldState, tracks how the world changes between
snapshots (WorldDiff), resolves element queries for actions, and
serializes a confidence-annotated view for the planner.

The planner never learns which provider saw what; it receives the best
fused version of the environment. Provider failures are isolated and
recorded — one broken source degrades fidelity, never the run.
"""
from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Optional

from .config import EngineConfig
from .contracts import (
    ProviderReport,
    SourceType,
    UIElement,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from .fusion import FusionEngine, normalize_text, text_similarity
from .providers import COST_EXPENSIVE, FrameContext, PerceptionProvider


class WorldModel:
    def __init__(self, config: EngineConfig, providers: list[PerceptionProvider]):
        self._config = config
        self._providers = list(providers)
        self._fusion = FusionEngine(config)
        self._last: Optional[WorldState] = None
        self.last_diff: Optional[WorldDiff] = None
        # Cumulative provider health for TaskResult metadata / benchmarks.
        self._stats: dict[str, dict] = {}
        self._snapshots = 0

    @property
    def last(self) -> Optional[WorldState]:
        return self._last

    # ----------------------------------------------------------- snapshot

    def snapshot(self, mode: str = "fast", force_refresh: bool = False,
                 region=None) -> WorldState:
        """Perceive the environment. fast = cheap providers only;
        full = escalate to expensive providers (vision LLM)."""
        now = time.time()
        if (
            not force_refresh
            and self._last is not None
            and self._last.mode == mode
            and (now - self._last.timestamp) < self._config.fast_cache_ttl_s
        ):
            return self._last

        frame = FrameContext(timestamp=now, region=region, force_refresh=force_refresh)
        observations = []
        reports: list[ProviderReport] = []
        for provider in self._providers:
            if mode != "full" and provider.cost == COST_EXPENSIVE:
                continue
            try:
                if not provider.available():
                    continue
            except Exception:
                continue
            source = provider.source.value if hasattr(provider.source, "value") else str(provider.source)
            t0 = time.time()
            try:
                found = provider.observe(frame) or []
                report = ProviderReport(
                    name=provider.name, source=source, ok=True,
                    observations=len(found),
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )
                observations.extend(found)
            except Exception as e:
                report = ProviderReport(
                    name=provider.name, source=source, ok=False,
                    latency_ms=round((time.time() - t0) * 1000, 1), error=str(e),
                )
            reports.append(report)
            self._record(report)

        world = self._build(observations, reports, frame, mode)
        self.last_diff = self.diff(self._last, world)
        self._last = world
        self._snapshots += 1
        return world

    def _build(self, observations, reports, frame: FrameContext, mode: str) -> WorldState:
        windows: list[WindowInfo] = []
        element_obs = []
        cursor = (-1, -1)
        page_context = ""
        seen_titles: set[str] = set()

        for obs in observations:
            if obs.role == "window":
                title = obs.text.strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                windows.append(
                    WindowInfo(
                        title=title,
                        focused=bool(obs.attributes.get("focused", False)),
                        z_order=int(obs.attributes.get("z_order", len(windows))),
                        bbox=obs.bbox,
                        process=str(obs.attributes.get("process", "")),
                        minimized=bool(obs.attributes.get("minimized", False)),
                    )
                )
            elif obs.role == "cursor":
                cursor = (int(obs.attributes.get("x", -1)), int(obs.attributes.get("y", -1)))
            elif obs.role == "screen":
                if obs.source == SourceType.VISION and obs.text:
                    page_context = obs.text
            elif obs.role == "process":
                continue  # reserved for future process providers
            else:
                element_obs.append(obs)

        windows.sort(key=lambda w: w.z_order)
        elements = self._fusion.fuse(element_obs)

        focused_window = next((w.title for w in windows if w.focused), "")
        if not focused_window:
            # UIA observations know their owning window even when the
            # metadata source couldn't report focus.
            focused_window = next((o.window for o in element_obs if o.window), "")

        focused_element_id = next((el.id for el in elements if el.focused), "")
        confidence = 0.0
        if elements:
            confidence = round(sum(el.confidence for el in elements) / len(elements), 3)

        return WorldState(
            timestamp=frame.timestamp,
            mode=mode,
            windows=windows,
            elements=elements,
            focused_window=focused_window,
            focused_element_id=focused_element_id,
            cursor=cursor,
            page_context=page_context,
            screenshot_path=frame.screenshot_path,
            providers=reports,
            confidence=confidence,
        )

    def _record(self, report: ProviderReport) -> None:
        entry = self._stats.setdefault(
            report.name, {"calls": 0, "failures": 0, "observations": 0, "latency_ms_total": 0.0}
        )
        entry["calls"] += 1
        entry["observations"] += report.observations
        entry["latency_ms_total"] += report.latency_ms
        if not report.ok:
            entry["failures"] += 1

    def stats(self) -> dict:
        """Cumulative perception stats for result metadata and benchmarks."""
        providers = {}
        for name, entry in self._stats.items():
            calls = max(1, entry["calls"])
            providers[name] = {
                "calls": entry["calls"],
                "failures": entry["failures"],
                "observations": entry["observations"],
                "avg_latency_ms": round(entry["latency_ms_total"] / calls, 1),
            }
        return {"snapshots": self._snapshots, "providers": providers}

    # --------------------------------------------------------------- diff

    @staticmethod
    def diff(before: Optional[WorldState], after: WorldState) -> WorldDiff:
        if before is None:
            return WorldDiff(changed=False, focus_after=after.focused_window,
                             summary="first observation")

        before_titles = {w.title for w in before.windows}
        after_titles = {w.title for w in after.windows}
        appeared = sorted(after_titles - before_titles)
        disappeared = sorted(before_titles - after_titles)

        focus_changed = (
            before.focused_window != after.focused_window
            and bool(before.focused_window or after.focused_window)
        )

        before_names = {normalize_text(el.name) for el in before.elements if el.name}
        after_names = {normalize_text(el.name) for el in after.elements if el.name}
        added = len(after_names - before_names)
        removed = len(before_names - after_names)

        text_sim = SequenceMatcher(
            None, before.screen_text[:4000], after.screen_text[:4000]
        ).ratio() if (before.screen_text or after.screen_text) else 1.0

        changed = bool(appeared or disappeared or focus_changed) or text_sim < 0.9

        parts = []
        if appeared:
            parts.append(f"windows appeared: {', '.join(appeared[:3])}")
        if disappeared:
            parts.append(f"windows closed: {', '.join(disappeared[:3])}")
        if focus_changed:
            parts.append(f"focus moved to '{after.focused_window}'")
        if added or removed:
            parts.append(f"{added} element(s) new, {removed} gone")
        if not parts:
            parts.append("no significant change" if not changed else "screen content changed")

        return WorldDiff(
            changed=changed,
            appeared_windows=appeared,
            disappeared_windows=disappeared,
            focus_before=before.focused_window,
            focus_after=after.focused_window,
            focus_changed=focus_changed,
            elements_added=added,
            elements_removed=removed,
            text_similarity=round(text_sim, 3),
            summary="; ".join(parts),
        )

    # --------------------------------------------------------------- find

    @staticmethod
    def find(world: WorldState, query: str,
             require_position: bool = True) -> Optional[UIElement]:
        """Resolve a query to the best matching element. Interactive
        elements win ties; confidence breaks the rest. Returns None when
        nothing plausibly matches — no blind guesses."""
        q = normalize_text(query)
        if not q:
            return None

        best: tuple[tuple, UIElement] | None = None
        for el in world.elements:
            if require_position and not el.has_position:
                continue
            score = _match_score(el, q)
            if score <= 0:
                continue
            key = (score, 1 if el.interactive else 0, el.confidence)
            if best is None or key > best[0]:
                best = (key, el)
        return best[1] if best else None

    # ----------------------------------------------------------- describe

    def describe(self, world: WorldState) -> str:
        """Planner-facing world view: structured, confidence-annotated,
        token-budgeted. This replaces raw OCR dumps."""
        lines: list[str] = []
        if world.focused_window:
            lines.append(f"Focused window: {world.focused_window}")
        if world.windows:
            titles = [w.title + (" (minimized)" if w.minimized else "")
                      for w in world.windows[:10]]
            lines.append("Open windows (front to back): " + " | ".join(titles))
        if world.page_context:
            lines.append(f"Screen context: {world.page_context}")

        interactive = [el for el in world.elements if el.interactive and el.name]
        if interactive:
            lines.append("Interactive elements (name [role] confidence):")
            for el in interactive[: self._config.describe_max_elements]:
                marker = "" if el.confidence >= 0.5 else " ?"
                state = "" if el.enabled else " (disabled)"
                focus = " (focused)" if el.focused else ""
                lines.append(
                    f'- "{el.name}" [{el.role}] {int(el.confidence * 100)}%{marker}{state}{focus}'
                )

        text_elements = [el for el in world.elements if not el.interactive and el.name]
        if text_elements:
            lines.append("Visible text:")
            budget = self._config.describe_max_chars - sum(len(line) for line in lines)
            used = 0
            for el in text_elements:
                if used + len(el.name) > max(budget, 400):
                    lines.append("- ... (more text truncated)")
                    break
                lines.append(f"- {el.name}")
                used += len(el.name)

        if not world.elements and not world.windows:
            lines.append("Nothing observable on screen.")
        return "\n".join(lines)


def _match_score(el: UIElement, normalized_query: str) -> float:
    """How well an element answers a query. Exact > prefix > substring >
    fuzzy; the element's description (vision) can also match."""
    candidates = [el.name, el.value, str(el.attributes.get("description", ""))]
    best = 0.0
    for candidate in candidates:
        c = normalize_text(candidate)
        if not c:
            continue
        if c == normalized_query:
            score = 1.0
        elif c.startswith(normalized_query) or normalized_query.startswith(c):
            score = 0.9
        elif normalized_query in c:
            score = 0.8
        elif c in normalized_query and len(c) >= 3:
            # Element name inside the query ("Submit" for "the Submit button").
            score = 0.7
        else:
            ratio = text_similarity(c, normalized_query)
            score = ratio if ratio >= 0.82 else 0.0
        best = max(best, score)
    return best
