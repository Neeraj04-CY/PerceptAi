"""The reasoning engine: the runtime's continuously evolving thought process.

Owns the per-cycle loop of questions — what do I know (beliefs), what
don't I know (uncertainty), am I closer to the goal (progress), what
should happen next (decision) — and keeps every answer observable. The
ExecutionEngine remains the ONE execution loop; this engine is the
session-owned service it consults each cycle. All reasoning here is
deterministic computation over signals the pipeline already produces;
LLM calls stay at the existing boundaries (plan, diagnose, judge).

Per-run mutable state lives in ReasoningState, owned by the engine run —
never module-level, never shared between sessions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field as dc_field
from typing import Callable, Optional

from .beliefs import BeliefState
from .budgets import ExecutionBudgetManager
from .config import EngineConfig
from .contracts import (
    ActionType,
    Decision,
    DecisionType,
    ExecutionState,
    GoalSpec,
    Hypothesis,
    ProgressEstimate,
    RecoveryOutcome,
    RecoveryPlan,
    Step,
    StepResult,
    StrategyProfile,
    TaskContext,
    UncertaintySignal,
    WorldDiff,
    WorldState,
)
from .decision import DecisionEngine, DecisionInputs
from .events import EventType
from .progress import ProgressEstimator
from .strategy import StrategyManager
from .uncertainty import UncertaintyTracker

Emitter = Callable[..., None]  # emit(EventType, **payload)

# Uncertainty signal kinds that point at perception itself — the ones
# vision escalation can actually help with.
_PERCEPTION_GAP_KINDS = {"low_perception_confidence", "provider_failed", "missing_window"}

_MAX_TRAJECTORY = 200  # cycles recorded for replay; runs are budget-bounded anyway


@dataclass
class ReasoningState:
    """Everything this run currently thinks. Owned by the engine run."""
    strategy: StrategyProfile
    goal: Optional[GoalSpec]
    emit: Emitter
    started_at: float
    beliefs: BeliefState = dc_field(default_factory=BeliefState)
    hypotheses: list[Hypothesis] = dc_field(default_factory=list)
    uncertainty: float = 0.0
    signals: list[UncertaintySignal] = dc_field(default_factory=list)
    progress: ProgressEstimate = dc_field(default_factory=ProgressEstimate)
    cycle: int = 0
    last_decision: Optional[Decision] = None
    decision_counts: dict = dc_field(default_factory=dict)
    decision_changes: int = 0
    steps_since_observation: int = 0
    steps_since_verification: int = 0
    consecutive_observations: int = 0
    goal_achieved_signal: bool = False
    planner_exhausted: bool = False  # last (re)plan produced nothing actionable
    post_launch_replan_pending: bool = False
    failure: Optional[StepResult] = None
    failure_is_constraint: bool = False
    recovery_attempted_for_failure: bool = False
    last_step: Optional[StepResult] = None
    trajectory: list[dict] = dc_field(default_factory=list)
    confidence_history: list[dict] = dc_field(default_factory=list)


class ReasoningEngine:
    def __init__(
        self,
        config: EngineConfig,
        strategies: Optional[StrategyManager] = None,
        uncertainty: Optional[UncertaintyTracker] = None,
        progress: Optional[ProgressEstimator] = None,
        decisions: Optional[DecisionEngine] = None,
        budgets: Optional[ExecutionBudgetManager] = None,
    ):
        self._config = config
        self.budgets = budgets or ExecutionBudgetManager(config)
        self.strategies = strategies or StrategyManager(config)
        self._uncertainty = uncertainty or UncertaintyTracker(config)
        self._progress = progress or ProgressEstimator(config)
        self._decisions = decisions or DecisionEngine(config, self.budgets)

    # ------------------------------------------------------------- begin

    def begin(self, goal: Optional[GoalSpec], context: TaskContext,
              emit: Emitter, started_at: Optional[float] = None) -> ReasoningState:
        strategy = self.strategies.select(goal) if goal else self.strategies.get("workflow")
        state = ReasoningState(
            strategy=strategy, goal=goal, emit=emit,
            started_at=started_at or time.time(),
        )
        emit(
            EventType.STRATEGY_SELECTED,
            strategy=strategy.name, description=strategy.description,
            reason=f"goal output format '{goal.output_format}'" if goal else "no analyzed goal",
        )
        # Recalled knowledge enters as low-confidence beliefs: memory can
        # inform this run, but only the live world can make it certain.
        for label, value in list(context.facts.items())[:15]:
            belief = state.beliefs.assert_belief(
                statement=f"{label}: {value[:120]}", kind="fact", subject=label,
                confidence=0.5, reason="recalled from memory", source="memory",
            )
            self._emit_belief(state, belief)
        return state

    # ----------------------------------------------------------- observing

    def observe(self, state: ReasoningState, world: WorldState,
                diff: Optional[WorldDiff], counted: bool = True) -> None:
        """Fold a fresh world snapshot into beliefs, uncertainty and progress."""
        for belief in state.beliefs.reconcile_with_world(world):
            self._emit_belief(state, belief)

        previous_score = state.uncertainty
        previous_kinds = {s.kind for s in state.signals}
        state.uncertainty, state.signals = self._uncertainty.assess(
            world, diff, state.last_step,
            contradicted_beliefs=state.beliefs.contradicted_count(),
        )
        if abs(state.uncertainty - previous_score) >= 0.1 or \
                {s.kind for s in state.signals} != previous_kinds:
            state.emit(
                EventType.UNCERTAINTY_CHANGED,
                score=state.uncertainty, previous=previous_score,
                signals=[{"kind": s.kind, "detail": s.detail, "severity": s.severity}
                         for s in state.signals[:8]],
            )

        state.confidence_history.append({
            "cycle": state.cycle,
            "world_confidence": world.confidence,
            "uncertainty": state.uncertainty,
            "progress": state.progress.completion,
        })
        if len(state.confidence_history) > _MAX_TRAJECTORY:
            del state.confidence_history[0]

        state.steps_since_observation = 0
        if counted:
            state.consecutive_observations += 1

    def verified(self, state: ReasoningState, world: WorldState,
                 diff: Optional[WorldDiff]) -> None:
        """A VERIFY cycle: same reconciliation as observe, but it also
        resets the verification cadence."""
        self.observe(state, world, diff, counted=False)
        state.steps_since_verification = 0
        state.consecutive_observations = 0

    # ------------------------------------------------------------ stepping

    def after_step(self, state: ReasoningState, result: StepResult,
                   context: TaskContext) -> None:
        """Turn a step outcome into beliefs. Action success is never taken
        as world truth — it seeds a belief that observation must confirm."""
        state.last_step = result
        state.steps_since_observation += 1
        state.steps_since_verification += 1
        state.consecutive_observations = 0

        step = result.step
        if not result.ok:
            state.failure = result
            state.failure_is_constraint = result.error.startswith("constraint")
            state.recovery_attempted_for_failure = False
            return

        if step.action == ActionType.OPEN_APP:
            app = str(step.params.get("app", ""))
            belief = state.beliefs.assert_belief(
                statement=f"{app} is open", kind="window_open", subject=app,
                confidence=0.7, reason="launch reported success", source="action",
            )
            self._emit_belief(state, belief)
        elif step.action == ActionType.NAVIGATE_URL:
            url = str(step.params.get("url", ""))
            belief = state.beliefs.assert_belief(
                statement=f"browser is at {url}", kind="action_effect", subject=url,
                confidence=0.7, reason="navigation reported success", source="action",
            )
            self._emit_belief(state, belief)
        elif step.action == ActionType.CLICK:
            element = str(result.data.get("element", step.params.get("find", "")))
            confidence = float(result.data.get("confidence", 0.6) or 0.6)
            belief = state.beliefs.assert_belief(
                statement=f"clicked '{element}'", kind="action_effect", subject=f"click:{element}",
                confidence=confidence, reason="click landed on a perceived element",
                source="action",
            )
            self._emit_belief(state, belief)
        elif step.action == ActionType.READ_SCREEN:
            for item in context.evidence[-int(result.data.get("evidence_count", 0)):]:
                belief = state.beliefs.assert_belief(
                    statement=f"{item.label}: {item.value[:120]}", kind="fact",
                    subject=item.label, confidence=item.confidence,
                    reason=f"observed on {item.source or 'screen'}", source="evidence",
                )
                self._emit_belief(state, belief)
        elif step.action in (ActionType.TYPE, ActionType.CLEAR_TYPE, ActionType.PRESS):
            belief = state.beliefs.assert_belief(
                statement=f"input sent: {step.description or step.action.value}",
                kind="action_effect", subject=f"input:{step.description[:60]}",
                confidence=0.75, reason="input reported success", source="action",
            )
            self._emit_belief(state, belief)

        if step.action in (ActionType.OPEN_APP, ActionType.NAVIGATE_URL):
            state.post_launch_replan_pending = True

    def failure_resolved(self, state: ReasoningState) -> None:
        state.failure = None
        state.failure_is_constraint = False
        state.recovery_attempted_for_failure = False

    # ------------------------------------------------------------ planning

    def record_plan(self, state: ReasoningState, steps: list[Step],
                    planner_said_done: bool, executed_count: int = 1) -> None:
        state.post_launch_replan_pending = False
        # A planner declaring the goal "already done" before ANY action has
        # run, while the goal still has unmet completion criteria, is a
        # hallucination — an action goal cannot be complete before it acts.
        # Reject the false signal so the run does not finish having done
        # nothing (measured: a data-entry task ended in 5s, zero steps,
        # because the first plan returned []).
        if (planner_said_done and executed_count == 0
                and state.goal is not None
                and getattr(state.goal, "completion_criteria", None)):
            planner_said_done = False
            steps = []  # force the exhausted path -> honest "could not plan"
        # A planner that produced nothing (and did not declare the goal
        # done) cannot be asked again for the same world — the decision
        # engine finishes instead of burning the replan budget.
        state.planner_exhausted = not steps and not planner_said_done
        if planner_said_done:
            state.goal_achieved_signal = True

    # ------------------------------------------------------------ recovery

    def record_recovery(self, state: ReasoningState, plan: RecoveryPlan,
                        attempt: int) -> None:
        known = {h.id for h in state.hypotheses}
        for hypothesis in plan.hypotheses:
            if hypothesis.id in known:
                continue
            state.hypotheses.append(hypothesis)
            state.emit(
                EventType.HYPOTHESIS_CREATED,
                subject=hypothesis.subject, explanation=hypothesis.explanation,
                kind=hypothesis.kind, probability=hypothesis.probability,
                source=hypothesis.source,
            )
        state.recovery_attempted_for_failure = True
        state.emit(
            EventType.RECOVERY_STARTED,
            attempt=attempt, subject=plan.subject,
            hypotheses=[{"kind": h.kind, "explanation": h.explanation,
                         "probability": h.probability} for h in plan.hypotheses[:6]],
            chosen=plan.chosen.explanation if plan.chosen else "",
            confidence=plan.confidence,
        )

    def record_recovery_outcome(self, state: ReasoningState, plan: RecoveryPlan,
                                outcome: RecoveryOutcome) -> None:
        if plan.chosen is not None and plan.chosen.status != "open":
            state.emit(
                EventType.HYPOTHESIS_RESOLVED,
                explanation=plan.chosen.explanation, kind=plan.chosen.kind,
                status=plan.chosen.status, reason=plan.chosen.resolution_reason,
            )
        state.emit(
            EventType.RECOVERY_COMPLETED,
            recovered=outcome.recovered, hypothesis=outcome.hypothesis_explanation,
            steps_executed=outcome.steps_executed, world_changed=outcome.world_changed,
            detail=outcome.detail,
        )

    def rejected_kinds(self, state: ReasoningState) -> set[str]:
        return {h.kind for h in state.hypotheses if h.status == "rejected"}

    # ------------------------------------------------------------ deciding

    def decide(self, state: ReasoningState, queue_len: int,
               execution: ExecutionState, context: TaskContext,
               executed: list[StepResult], llm_calls: int,
               constraint_abort: str = "") -> Decision:
        state.cycle += 1
        budget = self.budgets.snapshot(
            execution, state.started_at, llm_calls, execution.vision_escalations
        )

        previous = state.progress
        state.progress = self._progress.estimate(
            state.goal, state.beliefs, context.evidence, executed, budget,
            state.uncertainty, state.goal_achieved_signal, previous,
        )
        if (abs(state.progress.completion - previous.completion) >= 0.05
                or state.progress.objectives_met != previous.objectives_met):
            state.emit(
                EventType.PROGRESS_UPDATED,
                completion=state.progress.completion,
                confidence=state.progress.confidence,
                objectives_met=state.progress.objectives_met,
                objectives_total=state.progress.objectives_total,
                risk=state.progress.risk,
                remaining_work=state.progress.remaining_work,
                expected_remaining_s=state.progress.expected_remaining_s,
            )

        decision = self._decisions.decide(DecisionInputs(
            budget=budget,
            strategy=state.strategy,
            progress=state.progress,
            uncertainty=state.uncertainty,
            queue_len=queue_len,
            executed_count=len(executed),
            failure_pending=state.failure is not None,
            failure_is_constraint=state.failure_is_constraint,
            recovery_attempted_for_failure=state.recovery_attempted_for_failure,
            goal_achieved_signal=state.goal_achieved_signal,
            planner_exhausted=state.planner_exhausted,
            post_launch_replan_pending=state.post_launch_replan_pending,
            goal=state.goal,
            steps_since_observation=state.steps_since_observation,
            steps_since_verification=state.steps_since_verification,
            consecutive_observations=state.consecutive_observations,
            perception_gap=any(s.kind in _PERCEPTION_GAP_KINDS for s in state.signals),
            constraint_abort=constraint_abort,
        ))

        changed = state.last_decision is None or decision.type != state.last_decision.type
        if changed and state.last_decision is not None:
            state.decision_changes += 1
        state.last_decision = decision
        state.decision_counts[decision.type.value] = \
            state.decision_counts.get(decision.type.value, 0) + 1

        state.emit(
            EventType.DECISION_MADE,
            cycle=state.cycle, decision=decision.type.value,
            reason=decision.reason, changed=changed, factors=decision.factors,
            budget=budget.to_dict(),
        )
        state.trajectory.append({
            "cycle": state.cycle, "decision": decision.type.value,
            "reason": decision.reason, "uncertainty": state.uncertainty,
            "progress": state.progress.completion, "queue": queue_len,
        })
        if len(state.trajectory) > _MAX_TRAJECTORY:
            del state.trajectory[0]
        return decision

    # -------------------------------------------------------------- report

    def summary(self, state: ReasoningState) -> dict:
        """Replayable reasoning record for TaskResult metadata: why this
        run did what it did, in data."""
        confirmed = sum(1 for h in state.hypotheses if h.status == "confirmed")
        rejected = sum(1 for h in state.hypotheses if h.status == "rejected")
        return {
            "strategy": state.strategy.name,
            "cycles": state.cycle,
            "decisions": dict(state.decision_counts),
            "decision_changes": state.decision_changes,
            "final_progress": state.progress.to_dict(),
            "final_uncertainty": state.uncertainty,
            "uncertainty_signals": [
                {"kind": s.kind, "detail": s.detail, "severity": s.severity}
                for s in state.signals[:8]
            ],
            "beliefs": state.beliefs.summary(limit=10),
            "hypotheses": {
                "created": len(state.hypotheses),
                "confirmed": confirmed,
                "rejected": rejected,
                "open": len(state.hypotheses) - confirmed - rejected,
            },
            "trajectory": list(state.trajectory),
            "confidence_history": list(state.confidence_history),
        }

    # ------------------------------------------------------------ internal

    @staticmethod
    def _emit_belief(state: ReasoningState, belief) -> None:
        last = belief.history[-1] if belief.history else None
        state.emit(
            EventType.BELIEF_UPDATED,
            statement=belief.statement, kind=belief.kind, subject=belief.subject,
            confidence=belief.confidence,
            delta=last.delta if last else belief.confidence,
            reason=last.reason if last else "", source=last.source if last else "",
            supports=belief.supports, contradictions=belief.contradictions,
        )
