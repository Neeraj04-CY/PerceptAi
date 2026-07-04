"""Uncertainty tracking: the runtime knows when it is unsure, and why.

Every source of doubt becomes a typed UncertaintySignal derived from
signals the pipeline already produces — world confidence, provider
reports, element ambiguity, world diffs, contradicted beliefs. The
overall score combines signals noisy-OR style (consistent with the
confidence model) so independent doubts compound honestly.

Pure logic, deterministic, no LLM calls. Uncertainty must be cheap to
compute — it runs every reasoning cycle.
"""
from __future__ import annotations

from itertools import combinations
from typing import Optional

from .config import EngineConfig
from .contracts import StepResult, UncertaintySignal, WorldDiff, WorldState
from .fusion import text_similarity

# Actions whose success is expected to change the observable world.
_EXPECT_CHANGE = {"open_app", "navigate_url", "click", "navigate", "clear_type"}


class UncertaintyTracker:
    def __init__(self, config: EngineConfig):
        self._config = config

    def assess(
        self,
        world: Optional[WorldState],
        diff: Optional[WorldDiff] = None,
        last_step: Optional[StepResult] = None,
        contradicted_beliefs: int = 0,
    ) -> tuple[float, list[UncertaintySignal]]:
        """Score how uncertain the agent should be right now (0..1),
        with the concrete signals that produced the score."""
        signals: list[UncertaintySignal] = []
        if world is None:
            return 1.0, [UncertaintySignal(
                kind="low_perception_confidence",
                detail="no world observation available", severity=1.0,
            )]

        signals.extend(self._perception_signals(world))
        signals.extend(self._ambiguity_signals(world))
        signals.extend(self._effect_signals(diff, last_step))

        if contradicted_beliefs > 0:
            signals.append(UncertaintySignal(
                kind="contradicted_belief",
                detail=f"{contradicted_beliefs} belief(s) contradicted by the live world",
                severity=min(0.9, 0.3 * contradicted_beliefs),
            ))

        score = 0.0
        for signal in signals:
            score = score + signal.severity - score * signal.severity  # noisy-OR
        return round(min(score, 0.99), 3), signals

    # ------------------------------------------------------------ internal

    def _perception_signals(self, world: WorldState) -> list[UncertaintySignal]:
        signals: list[UncertaintySignal] = []
        if world.elements and world.confidence < self._config.low_confidence_threshold:
            signals.append(UncertaintySignal(
                kind="low_perception_confidence",
                detail=f"world confidence {world.confidence:.2f} below "
                       f"{self._config.low_confidence_threshold:.2f}",
                severity=round(min(0.8, self._config.low_confidence_threshold - world.confidence + 0.3), 3),
            ))
        if not world.elements and not world.windows:
            signals.append(UncertaintySignal(
                kind="missing_window",
                detail="nothing observable on screen", severity=0.7,
            ))
        for report in world.providers:
            if not report.ok:
                signals.append(UncertaintySignal(
                    kind="provider_failed",
                    detail=f"{report.name} failed: {report.error[:80]}", severity=0.35,
                ))
            elif report.latency_ms > self._config.slow_provider_ms:
                signals.append(UncertaintySignal(
                    kind="slow_provider",
                    detail=f"{report.name} took {report.latency_ms:.0f}ms "
                           f"(app may be loading or busy)",
                    severity=0.2,
                ))
        return signals

    def _ambiguity_signals(self, world: WorldState) -> list[UncertaintySignal]:
        """Two elements with nearly identical names is exactly the
        situation where a confident click is a wrong click. Interactive
        elements are checked when a source knows interactivity; on
        OCR-only screens every named element is a click candidate."""
        named = ([el for el in world.interactive_elements if el.name]
                 or [el for el in world.elements if el.name])[:30]
        pairs = []
        for a, b in combinations(named, 2):
            if self._confusable(a.name, b.name):
                pairs.append((a.name, b.name))
            if len(pairs) >= 3:
                break
        return [
            UncertaintySignal(
                kind="ambiguous_elements",
                detail=f"similar labels: '{a}' vs '{b}'", severity=0.3,
            )
            for a, b in pairs
        ]

    def _confusable(self, a: str, b: str) -> bool:
        if a == b or text_similarity(a, b) >= self._config.ambiguity_similarity:
            return True
        # Same leading word ("Submit Order" / "Submit Query"): exactly what
        # a planner's short 'find' query cannot distinguish.
        first_a = a.split()[0].casefold() if a.split() else ""
        first_b = b.split()[0].casefold() if b.split() else ""
        return bool(first_a) and len(first_a) >= 4 and first_a == first_b and a != b

    @staticmethod
    def _effect_signals(diff: Optional[WorldDiff],
                        last_step: Optional[StepResult]) -> list[UncertaintySignal]:
        if diff is None or last_step is None or not last_step.ok:
            return []
        if last_step.step.action.value in _EXPECT_CHANGE and not diff.changed:
            return [UncertaintySignal(
                kind="no_change_after_action",
                detail=f"'{last_step.step.description}' reported success "
                       f"but the world did not observably change",
                severity=0.4,
            )]
        return []
