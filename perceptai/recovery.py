"""Recovery management: understand the failure, then fix the cause.

Recovery is never "retry the click". One attempt is: generate every
plausible explanation (deterministic signals + the healer's ranked LLM
diagnoses — one LLM call), choose the most probable hypothesis that
grounds a concrete recovery, and after the runtime executes it, MEASURE
what happened and resolve the hypothesis honestly. Rejected hypotheses
stay rejected; alternatives stay alive for the next attempt.

The runtime owns step execution; this module owns recovery reasoning.
The healer remains the single LLM diagnosis path — no duplicated reasoning.
"""
from __future__ import annotations

from typing import Optional

from .config import EngineConfig
from .contracts import (
    Hypothesis,
    RecoveryOutcome,
    RecoveryPlan,
    Step,
    WorldDiff,
    WorldState,
)
from .healer import Healer
from .hypothesis import HypothesisGenerator


class RecoveryManager:
    def __init__(self, config: EngineConfig, healer: Healer,
                 hypotheses: HypothesisGenerator):
        self._config = config
        self._healer = healer
        self._hypotheses = hypotheses

    def plan(
        self,
        failed_step: Step,
        error: str,
        world_view: str,
        world: Optional[WorldState],
        diff: Optional[WorldDiff],
        expected_window: str = "",
        rejected_kinds: Optional[set[str]] = None,
    ) -> RecoveryPlan:
        """Build the hypothesis set for this failure and choose the best
        actionable explanation. Kinds already disproven in earlier attempts
        are not chosen again."""
        subject = f"{failed_step.action.value} '{failed_step.description}' failed"
        candidates = self._hypotheses.generate(
            failed_step, error, world, diff, expected_window
        )
        try:
            healing = self._healer.diagnose(failed_step, error or "step failed", world_view)
        except Exception:
            healing = None
        if healing is not None:
            candidates = self._hypotheses.merge_llm(candidates, healing, subject)

        rejected = rejected_kinds or set()
        chosen: Optional[Hypothesis] = None
        for candidate in candidates:  # already sorted by probability
            if candidate.kind in rejected or not candidate.recovery_steps:
                continue
            if candidate.probability > self._config.healing_confidence_threshold:
                chosen = candidate
                break

        return RecoveryPlan(
            subject=subject,
            hypotheses=candidates,
            chosen=chosen,
            steps=list(chosen.recovery_steps) if chosen else [],
            confidence=chosen.probability if chosen else 0.0,
        )

    def assess(self, plan: RecoveryPlan, steps_executed: int,
               all_steps_ok: bool, world_changed: bool,
               condition_cleared: bool) -> RecoveryOutcome:
        """Resolve the chosen hypothesis against what was MEASURED, not
        what was attempted. Recovery actions merely running is not
        recovery — the original failure condition must no longer hold.
        A disproven explanation is rejected so the next attempt tries a
        different one; a confirmed one is recorded with its evidence."""
        if plan.chosen is None:
            return RecoveryOutcome(
                recovered=False,
                detail="no hypothesis grounded a viable recovery",
            )
        recovered = all_steps_ok and condition_cleared
        if recovered:
            reason = "recovery actions succeeded and the failure condition cleared"
            if world_changed:
                reason += "; the world visibly changed"
            self._hypotheses.resolve(plan.chosen, confirmed=True, reason=reason)
        elif all_steps_ok:
            self._hypotheses.resolve(
                plan.chosen, confirmed=False,
                reason="recovery actions ran but the failure condition still holds",
            )
        else:
            self._hypotheses.resolve(
                plan.chosen, confirmed=False,
                reason="recovery actions for this explanation failed",
            )
        return RecoveryOutcome(
            recovered=recovered,
            hypothesis_kind=plan.chosen.kind,
            hypothesis_explanation=plan.chosen.explanation,
            steps_executed=steps_executed,
            world_changed=world_changed,
            detail=plan.chosen.resolution_reason,
        )
