"""Belief state: what the agent currently holds true, with honest confidence.

Beliefs evolve, they are never overwritten. Supporting evidence raises
confidence noisy-OR style (consistent with perception fusion, capped at
0.99); contradictions lower it multiplicatively (floored above 0, because
absence of evidence is not proof of absence). Every change is recorded as
a BeliefUpdate so any run can be replayed decision by decision.

Per-run mutable state owned by the reasoning layer — never module-level.
Cross-task knowledge stays in MemoryStore; BeliefState is about THIS run.
Pure logic, deterministic, no LLM calls.
"""
from __future__ import annotations

import uuid
from typing import Optional

from .contracts import Belief, BeliefUpdate, WorldState, utc_now_iso
from .fusion import normalize_text

_MAX_HISTORY = 25  # per belief; enough for replay without unbounded growth
_CONFIDENCE_CAP = 0.99
_CONFIDENCE_FLOOR = 0.02


class BeliefState:
    def __init__(self) -> None:
        self._beliefs: dict[tuple[str, str], Belief] = {}

    # ------------------------------------------------------------- writing

    def assert_belief(self, statement: str, kind: str, subject: str,
                      confidence: float, reason: str, source: str = "") -> Belief:
        """Create a belief, or reinforce it if already held. Agreement
        compounds confidence; it never fabricates certainty."""
        confidence = max(0.0, min(_CONFIDENCE_CAP, confidence))
        key = self._key(kind, subject)
        belief = self._beliefs.get(key)
        if belief is None:
            belief = Belief(
                id=str(uuid.uuid4())[:8], statement=statement,
                kind=kind, subject=subject, confidence=confidence, supports=1,
            )
            belief.history.append(BeliefUpdate(
                at=belief.created_at, delta=confidence,
                confidence=confidence, reason=reason, source=source,
            ))
            self._beliefs[key] = belief
            return belief

        previous = belief.confidence
        belief.confidence = round(
            min(_CONFIDENCE_CAP, previous + confidence - previous * confidence), 3
        )  # noisy-OR: independent agreement compounds
        belief.supports += 1
        belief.statement = statement or belief.statement
        self._record(belief, previous, reason, source)
        return belief

    def contradict(self, kind: str, subject: str, strength: float,
                   reason: str, source: str = "") -> Optional[Belief]:
        """Weaken a belief. strength 1.0 collapses it to the floor;
        weaker contradictions merely erode confidence."""
        belief = self._beliefs.get(self._key(kind, subject))
        if belief is None:
            return None
        strength = max(0.0, min(1.0, strength))
        previous = belief.confidence
        belief.confidence = round(
            max(_CONFIDENCE_FLOOR, previous * (1.0 - strength)), 3
        )
        belief.contradictions += 1
        self._record(belief, previous, reason, source)
        return belief

    # ----------------------------------------------------- reconciliation

    def reconcile_with_world(self, world: WorldState) -> list[Belief]:
        """Hold beliefs up against a fresh observation. Window beliefs are
        directly checkable: a window that is visible corroborates, one
        that is gone contradicts. Returns every belief that moved."""
        changed: list[Belief] = []
        titles = [normalize_text(w.title) for w in world.windows]
        for belief in self._beliefs.values():
            if belief.kind != "window_open" or not belief.subject:
                continue
            subject = normalize_text(belief.subject)
            visible = any(subject in title or title in subject for title in titles if title)
            previous = belief.confidence
            if visible:
                self.assert_belief(
                    belief.statement, belief.kind, belief.subject,
                    confidence=0.9, reason="window visible in live world", source="world",
                )
            else:
                self.contradict(
                    belief.kind, belief.subject, strength=0.5,
                    reason="window not visible in live world", source="world",
                )
            if belief.confidence != previous:
                changed.append(belief)
        return changed

    # ------------------------------------------------------------- reading

    def get(self, kind: str, subject: str) -> Optional[Belief]:
        return self._beliefs.get(self._key(kind, subject))

    def all(self) -> list[Belief]:
        return sorted(self._beliefs.values(), key=lambda b: b.confidence, reverse=True)

    def contradicted_count(self, min_drop: float = 0.2) -> int:
        """Beliefs that have taken real damage — feeds uncertainty."""
        count = 0
        for belief in self._beliefs.values():
            if belief.contradictions and belief.confidence < (1.0 - min_drop):
                count += 1
        return count

    def summary(self, limit: int = 10) -> list[dict]:
        return [b.to_dict() for b in self.all()[:limit]]

    # ------------------------------------------------------------ internal

    @staticmethod
    def _key(kind: str, subject: str) -> tuple[str, str]:
        return kind, normalize_text(subject)

    @staticmethod
    def _record(belief: Belief, previous: float, reason: str, source: str) -> None:
        belief.updated_at = utc_now_iso()
        belief.history.append(BeliefUpdate(
            at=belief.updated_at, delta=round(belief.confidence - previous, 3),
            confidence=belief.confidence, reason=reason, source=source,
        ))
        if len(belief.history) > _MAX_HISTORY:
            del belief.history[0]
