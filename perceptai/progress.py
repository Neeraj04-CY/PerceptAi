"""Progress estimation: how close is the BUSINESS outcome, not the step queue.

Completion derives from goal semantics — which objectives have supporting
beliefs/evidence, which completion criteria the collected evidence covers,
and whether the planner has signalled "goal achieved". Executed step
counts are used only to estimate remaining time, never as progress.

Pure logic, deterministic, no LLM calls — it runs every reasoning cycle.
"""
from __future__ import annotations

from typing import Optional

from .beliefs import BeliefState
from .config import EngineConfig
from .contracts import (
    BudgetSnapshot,
    Evidence,
    GoalSpec,
    ProgressEstimate,
    StepResult,
)
from .fusion import normalize_text, text_similarity

_STEPS_PER_OBJECTIVE = 2  # planning heuristic for remaining-work estimates


class ProgressEstimator:
    def __init__(self, config: EngineConfig):
        self._config = config

    def estimate(
        self,
        goal: Optional[GoalSpec],
        beliefs: BeliefState,
        evidence: list[Evidence],
        executed: list[StepResult],
        budget: BudgetSnapshot,
        uncertainty: float,
        goal_achieved_signal: bool = False,
        previous: Optional[ProgressEstimate] = None,
    ) -> ProgressEstimate:
        objectives = list(goal.objectives) if goal else []
        criteria = list(goal.completion_criteria) if goal else []

        objectives_met = sum(
            1 for o in objectives if self._objective_supported(o, beliefs, evidence, executed)
        )
        criteria_supported = sum(
            1 for c in criteria if self._criterion_supported(c, evidence)
        )

        completion = self._completion(
            objectives, objectives_met, criteria, criteria_supported, goal_achieved_signal
        )

        stalled = 0
        if previous is not None and completion <= previous.completion + 1e-9:
            stalled = previous.stalled_cycles + 1

        recent_failure = bool(executed) and not executed[-1].ok
        risk = _noisy_or(
            budget.pressure * 0.5,
            uncertainty * 0.4,
            0.3 if recent_failure else 0.0,
            min(0.45, 0.15 * stalled),
        )

        remaining_objectives = max(0, len(objectives) - objectives_met)
        expected_steps = 0 if goal_achieved_signal else max(
            0, min(remaining_objectives * _STEPS_PER_OBJECTIVE,
                   budget.steps_max - budget.steps_used),
        )
        avg_step_s = (
            sum(r.duration_s for r in executed) / len(executed) if executed else 2.0
        )
        expected_s = round(expected_steps * (avg_step_s + self._config.settle_after_step_s), 1)

        # How much to trust the estimate itself: checkable goals (criteria,
        # evidence) make it firmer; uncertainty erodes it.
        estimate_confidence = 0.4
        if criteria:
            estimate_confidence += 0.2
        if evidence:
            estimate_confidence += 0.2
        if goal_achieved_signal:
            estimate_confidence += 0.2
        estimate_confidence = round(max(0.05, estimate_confidence - uncertainty * 0.3), 3)

        return ProgressEstimate(
            completion=completion,
            confidence=estimate_confidence,
            objectives_total=len(objectives),
            objectives_met=objectives_met,
            criteria_total=len(criteria),
            criteria_supported=criteria_supported,
            remaining_work=self._remaining_summary(
                objectives, beliefs, evidence, executed, goal_achieved_signal
            ),
            expected_remaining_steps=expected_steps,
            expected_remaining_s=expected_s,
            risk=round(risk, 3),
            stalled_cycles=stalled,
        )

    # ------------------------------------------------------------ internal

    @staticmethod
    def _completion(objectives: list[str], objectives_met: int,
                    criteria: list[str], criteria_supported: int,
                    goal_achieved_signal: bool) -> float:
        if goal_achieved_signal:
            # The planner examined the live world and declared the goal met.
            # Strong signal, but final verification still owns the last word.
            return 0.95
        parts: list[float] = []
        if objectives:
            parts.append(objectives_met / len(objectives))
        if criteria:
            parts.append(criteria_supported / len(criteria))
        if not parts:
            return 0.0
        return round(sum(parts) / len(parts), 3)

    @staticmethod
    def _objective_supported(objective: str, beliefs: BeliefState,
                             evidence: list[Evidence],
                             executed: list[StepResult]) -> bool:
        """An objective counts as met only when something OBSERVED backs it:
        a live belief, collected evidence, or a completed step whose meaning
        matches the objective."""
        for belief in beliefs.all():
            if belief.confidence >= 0.6 and _text_overlap(belief.statement, objective):
                return True
        for item in evidence:
            if _text_overlap(f"{item.label} {item.value}", objective):
                return True
        for result in executed:
            if result.ok and text_similarity(result.step.description, objective) >= 0.6:
                return True
        return False

    @staticmethod
    def _criterion_supported(criterion: str, evidence: list[Evidence]) -> bool:
        return any(
            _text_overlap(f"{item.label} {item.value}", criterion) for item in evidence
        )

    @staticmethod
    def _remaining_summary(objectives: list[str], beliefs: BeliefState,
                           evidence: list[Evidence], executed: list[StepResult],
                           goal_achieved_signal: bool) -> str:
        if goal_achieved_signal:
            return "confirm and report"
        unmet = [
            o for o in objectives
            if not ProgressEstimator._objective_supported(o, beliefs, evidence, executed)
        ]
        if not unmet:
            return "verify outcome" if objectives else "no measurable objectives"
        return "; ".join(unmet[:3])


def _noisy_or(*severities: float) -> float:
    """Independent risk factors compound without ever exceeding 1."""
    score = 0.0
    for severity in severities:
        severity = max(0.0, min(1.0, severity))
        score = score + severity - score * severity
    return min(score, 0.99)


def _text_overlap(text: str, target: str) -> bool:
    """Token-level containment: enough meaningful words of the target
    appear in the text. Cheap and honest — fuzzier than an LLM judge,
    which verification still applies at the end."""
    text_n = normalize_text(text)
    words = [w for w in normalize_text(target).split() if len(w) >= 4]
    if not words or not text_n:
        return False
    hits = sum(1 for w in words if w in text_n)
    return hits / len(words) >= 0.5
