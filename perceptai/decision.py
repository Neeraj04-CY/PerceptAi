"""The decision engine: one typed verdict per reasoning cycle.

Control flow used to be if/else buried in the runtime. Now every cycle
produces a Decision — continue, observe, escalate perception, verify,
replan, recover, finish, abort — chosen by explicit, ordered rules over
the current beliefs, uncertainty, progress and budgets. The factors that
produced each decision travel with it, so a developer can always answer
"why did the agent do this?" from the event stream alone.

Pure function of its inputs: deterministic, replayable, no LLM calls.
The runtime executes decisions; it never overrides them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .budgets import ExecutionBudgetManager
from .config import EngineConfig
from .contracts import (
    BudgetSnapshot,
    Decision,
    DecisionType,
    GoalSpec,
    ProgressEstimate,
    StrategyProfile,
)


@dataclass
class DecisionInputs:
    """Everything the decision engine is allowed to know. Assembled by the
    reasoning engine each cycle — the runtime never hand-crafts one."""
    budget: BudgetSnapshot
    strategy: StrategyProfile
    progress: ProgressEstimate
    uncertainty: float
    queue_len: int
    executed_count: int
    failure_pending: bool = False
    failure_is_constraint: bool = False
    recovery_attempted_for_failure: bool = False
    goal_achieved_signal: bool = False  # planner returned [] on the live world
    planner_exhausted: bool = False  # last (re)plan produced nothing actionable
    post_launch_replan_pending: bool = False
    goal: Optional[GoalSpec] = None
    steps_since_observation: int = 0
    steps_since_verification: int = 0
    consecutive_observations: int = 0
    perception_gap: bool = False  # uncertainty signals point at perception itself
    constraint_abort: str = ""  # non-empty: a constraint demands stopping


class DecisionEngine:
    def __init__(self, config: EngineConfig, budgets: ExecutionBudgetManager):
        self._config = config
        self._budgets = budgets

    def decide(self, inputs: DecisionInputs) -> Decision:
        """Ordered rules; the first that applies wins. Safety and budgets
        outrank progress; progress outranks caution; caution outranks speed."""
        b = inputs.budget
        factors = {
            "uncertainty": inputs.uncertainty,
            "progress": inputs.progress.completion,
            "risk": inputs.progress.risk,
            "budget_pressure": b.pressure,
            "queue": inputs.queue_len,
        }

        def make(type_: DecisionType, reason: str, **extra) -> Decision:
            return Decision(type=type_, reason=reason, factors={**factors, **extra})

        # 1. Hard stops: constraints and the wall clock outrank everything.
        if inputs.constraint_abort:
            return make(DecisionType.ABORT, f"constraint: {inputs.constraint_abort}")
        if self._budgets.time_exceeded(b):
            return make(DecisionType.ABORT,
                        f"time budget exhausted ({b.elapsed_s:.0f}s of {b.time_max_s:.0f}s)")

        # 2. An unresolved failure is dealt with before anything else.
        if inputs.failure_pending:
            if inputs.failure_is_constraint:
                # Policy denials are not healable — a different plan is.
                if self._budgets.can_replan(b):
                    return make(DecisionType.REPLAN, "step denied by constraint; plan around it")
                # Only the user can relax a policy. No interactive channel
                # exists yet, so the runtime finishes honestly with this
                # decision on record instead of pretending to abort a bug.
                return make(DecisionType.NEED_USER,
                            "a constraint blocks the only remaining path")
            if not inputs.recovery_attempted_for_failure and self._budgets.can_recover(b):
                return make(DecisionType.RECOVER, "step failed; diagnose before retrying")
            if self._budgets.can_replan(b):
                return make(DecisionType.REPLAN, "recovery did not resolve the failure")
            return make(DecisionType.ABORT, "failure could not be recovered or replanned")

        # 3. The planner looked at the live world and declared the goal met.
        if inputs.goal_achieved_signal:
            return make(DecisionType.FINISH, "planner confirmed the goal is achieved")

        # 4. Step budget: stop executing, salvage what we have.
        if not self._budgets.can_step(b):
            return make(DecisionType.FINISH, "step budget exhausted")

        # 5. The screen just changed structurally (launch/navigation):
        #    plans made before it are stale hypotheses.
        if inputs.post_launch_replan_pending:
            if self._budgets.can_replan(b):
                return make(DecisionType.REPLAN, "screen changed after launch")
            # No replan budget: fall through and run the existing queue.

        # 6. Empty queue: continue toward the goal or wrap up. (A pending
        #    post-launch replan only reaches here when replanning is not
        #    affordable, so finishing is the honest option.)
        if inputs.queue_len == 0:
            has_criteria = inputs.goal is not None and bool(inputs.goal.completion_criteria)
            if (has_criteria and inputs.executed_count > 0
                    and not inputs.planner_exhausted
                    and self._budgets.can_replan(b)):
                return make(DecisionType.REPLAN, "queue empty; checking goal completion")
            return make(DecisionType.FINISH,
                        "no steps remain" if inputs.executed_count else "nothing was planned")

        # 7. Too unsure to act: observe first. Perception-shaped doubt with
        #    budget escalates to the expensive providers; capped so an
        #    unobservable screen can never trap the loop.
        if (inputs.uncertainty > inputs.strategy.uncertainty_tolerance
                and inputs.consecutive_observations < 2):
            if (inputs.perception_gap
                    and inputs.strategy.perception_escalation != "reluctant"
                    and self._budgets.can_escalate_vision(b)):
                return make(DecisionType.ESCALATE_PERCEPTION,
                            f"uncertainty {inputs.uncertainty:.2f} looks like a perception gap")
            if inputs.steps_since_observation > 0:
                return make(DecisionType.OBSERVE,
                            f"uncertainty {inputs.uncertainty:.2f} above "
                            f"tolerance {inputs.strategy.uncertainty_tolerance:.2f}")

        # 8. Periodic belief verification; uncertainty shortens the interval.
        interval = max(1, round(
            inputs.strategy.verify_step_interval * (1.0 - 0.5 * inputs.uncertainty)
        ))
        if inputs.executed_count > 0 and inputs.steps_since_verification >= interval:
            return make(DecisionType.VERIFY,
                        f"verification due (every {interval} steps at "
                        f"uncertainty {inputs.uncertainty:.2f})")

        # 9. Nothing demands attention: execute the next step.
        return make(DecisionType.CONTINUE, "next planned step")


__all__ = ["DecisionEngine", "DecisionInputs"]
