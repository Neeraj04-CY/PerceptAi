"""The shared evidence graph: one evolving body of mission knowledge.

Every specialist's findings converge here. The same value from a new
source corroborates a claim (noisy-OR, capped 0.99 — the same formula
perception fusion uses); a credible different value becomes a new
version with the conflict left visible, never silently resolved.
Reports are generated from current claims only; durable persistence
stays in the ONE knowledge store (MemoryStore) — this graph is the
mission-scoped truth, not a second database.
"""
from __future__ import annotations

from typing import Optional

from .contracts import EntityRelation, Evidence, EvidenceClaim, utc_now_iso

_CONFLICT_CONFIDENCE = 0.5  # both sides at/above this = a real disagreement
_CONFIDENCE_CAP = 0.99


def _norm(text: str) -> str:
    return " ".join(str(text).split()).strip().lower()


class EvidenceGraph:
    def __init__(self) -> None:
        # (entity, attribute) -> version history, oldest first; last = current.
        self._claims: dict[tuple[str, str], list[EvidenceClaim]] = {}
        self.relations: list[EntityRelation] = []

    # ------------------------------------------------------------- writing

    def ingest(self, items: list[Evidence], entity: str = "") -> int:
        """Fold typed Evidence into claims. The entity hint (usually the
        work order's primary entity) scopes the claim; a label-only fact
        becomes its own entity. Returns how many claims changed."""
        changed = 0
        for item in items:
            if not str(item.value).strip():
                continue
            claim_entity = entity.strip() or item.label or "unknown"
            self.assert_claim(
                entity=claim_entity,
                attribute=item.label or item.kind,
                value=str(item.value),
                kind=item.kind,
                source=item.source or "screen",
                confidence=float(item.confidence or 0.5),
            )
            changed += 1
        return changed

    def assert_claim(self, entity: str, attribute: str, value: str,
                     kind: str = "text", source: str = "",
                     confidence: float = 0.5) -> EvidenceClaim:
        key = (_norm(entity), _norm(attribute))
        history = self._claims.setdefault(key, [])
        current = history[-1] if history else None

        if current is not None and _norm(current.value) == _norm(value):
            # Corroboration: confidence compounds, it is never overwritten down.
            combined = 1.0 - (1.0 - current.confidence) * (1.0 - confidence)
            current.confidence = min(_CONFIDENCE_CAP, combined)
            current.supports += 1
            current.last_seen = utc_now_iso()
            if source and source not in current.sources:
                current.sources.append(source)
            return current

        claim = EvidenceClaim(
            entity=entity, attribute=attribute, value=value, kind=kind,
            confidence=min(_CONFIDENCE_CAP, confidence),
            sources=[source] if source else [],
            version=(current.version + 1) if current is not None else 1,
        )
        history.append(claim)
        return claim

    def relate(self, subject: str, relation: str, obj: str,
               source: str = "", confidence: float = 0.5) -> EntityRelation:
        for existing in self.relations:
            if (_norm(existing.subject), _norm(existing.relation), _norm(existing.object)) \
                    == (_norm(subject), _norm(relation), _norm(obj)):
                existing.confidence = min(
                    _CONFIDENCE_CAP,
                    1.0 - (1.0 - existing.confidence) * (1.0 - confidence),
                )
                if source and source not in existing.sources:
                    existing.sources.append(source)
                return existing
        rel = EntityRelation(subject=subject, relation=relation, object=obj,
                             sources=[source] if source else [],
                             confidence=confidence)
        self.relations.append(rel)
        return rel

    # ------------------------------------------------------------- reading

    def current_claims(self) -> list[EvidenceClaim]:
        return [history[-1] for history in self._claims.values() if history]

    def claim(self, entity: str, attribute: str) -> Optional[EvidenceClaim]:
        history = self._claims.get((_norm(entity), _norm(attribute)))
        return history[-1] if history else None

    def for_entity(self, entity: str) -> list[EvidenceClaim]:
        needle = _norm(entity)
        return [h[-1] for (ent, _attr), h in self._claims.items() if ent == needle and h]

    def conflicts(self) -> list[dict]:
        """Open disagreements: two credible versions of the same claim.
        Conflicts are reported, never silently resolved."""
        found = []
        for (entity, attribute), history in self._claims.items():
            credible = [c for c in history if c.confidence >= _CONFLICT_CONFIDENCE]
            values = {_norm(c.value) for c in credible}
            if len(values) > 1:
                found.append({
                    "entity": entity, "attribute": attribute,
                    "values": [
                        {"value": c.value, "confidence": c.confidence,
                         "sources": list(c.sources), "version": c.version}
                        for c in credible
                    ],
                })
        return found

    def sources(self) -> list[str]:
        seen: list[str] = []
        for claim in self.current_claims():
            for source in claim.sources:
                if source and source not in seen:
                    seen.append(source)
        return seen

    def report_evidence(self, limit: int = 50) -> list[Evidence]:
        """Current claims as Evidence — the ONLY facts a mission report
        may be composed from (grounded, exactly like task reports)."""
        claims = sorted(self.current_claims(),
                        key=lambda c: (-c.confidence, c.entity, c.attribute))
        return [
            Evidence(
                kind=c.kind,
                label=(c.attribute if _norm(c.attribute) != _norm(c.entity)
                       else c.entity)[:120],
                value=c.value,
                source=", ".join(c.sources[:3]),
                confidence=c.confidence,
            )
            for c in claims[:limit]
        ]

    def summary(self) -> dict:
        claims = self.current_claims()
        return {
            "claims": len(claims),
            "entities": len({_norm(c.entity) for c in claims}),
            "relations": len(self.relations),
            "conflicts": len(self.conflicts()),
            "sources": len(self.sources()),
            "avg_confidence": round(
                sum(c.confidence for c in claims) / len(claims), 3
            ) if claims else 0.0,
        }

    # ---------------------------------------------------------- persistence

    def persist(self, memory, mission_id: str) -> None:
        """Durable knowledge goes through the ONE store the runtime already
        uses. Best-effort: persistence never affects the mission outcome."""
        try:
            memory.remember_evidence(mission_id, self.report_evidence())
        except Exception:
            pass
