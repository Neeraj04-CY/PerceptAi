"""ProgressEstimator: business progress, never step counts."""
from perceptai.beliefs import BeliefState
from perceptai.budgets import ExecutionBudgetManager
from perceptai.contracts import (
    ActionType,
    Evidence,
    ExecutionState,
    GoalSpec,
    ProgressEstimate,
    Step,
    StepResult,
    StepStatus,
)
from perceptai.progress import ProgressEstimator

import time

from tests.conftest import fast_config


def _budget(**state_overrides):
    manager = ExecutionBudgetManager(fast_config())
    return manager.snapshot(ExecutionState(**state_overrides), time.time(), 0, 0)


def _estimator():
    return ProgressEstimator(fast_config())


def _goal():
    return GoalSpec(
        intent="find the laptop price on the store page",
        objectives=["open the store page", "collect the laptop price"],
        completion_criteria=["laptop price is captured"],
        output_format="data",
    )


def test_no_support_means_no_progress():
    estimate = _estimator().estimate(
        _goal(), BeliefState(), [], [], _budget(), uncertainty=0.0,
    )
    assert estimate.completion == 0.0
    assert estimate.objectives_met == 0


def test_evidence_supports_objectives_and_criteria():
    evidence = [Evidence(kind="price", label="laptop price", value="$999",
                         source="store", confidence=0.9)]
    estimate = _estimator().estimate(
        _goal(), BeliefState(), evidence, [], _budget(), uncertainty=0.0,
    )
    assert estimate.objectives_met >= 1
    assert estimate.criteria_supported == 1
    assert estimate.completion > 0.4


def test_beliefs_support_objectives():
    beliefs = BeliefState()
    beliefs.assert_belief("store page is open", "window_open", "store page",
                          0.9, "launch ok", "action")
    estimate = _estimator().estimate(
        _goal(), beliefs, [], [], _budget(), uncertainty=0.0,
    )
    assert estimate.objectives_met >= 1


def test_step_counts_alone_do_not_move_progress():
    steps = [
        StepResult(step=Step(action=ActionType.WAIT, description=f"wait {i}"),
                   status=StepStatus.COMPLETED, index=i)
        for i in range(1, 6)
    ]
    estimate = _estimator().estimate(
        _goal(), BeliefState(), [], steps, _budget(steps_executed=5), uncertainty=0.0,
    )
    assert estimate.completion == 0.0  # five successful steps, zero business progress


def test_planner_done_signal_dominates():
    estimate = _estimator().estimate(
        _goal(), BeliefState(), [], [], _budget(), uncertainty=0.0,
        goal_achieved_signal=True,
    )
    assert estimate.completion == 0.95  # verification still owns the last word
    assert estimate.expected_remaining_steps == 0


def test_stall_counts_cycles_without_movement():
    previous = ProgressEstimate(completion=0.5, stalled_cycles=1)
    estimate = _estimator().estimate(
        GoalSpec(intent="x", objectives=["a", "b"]), BeliefState(), [], [],
        _budget(), uncertainty=0.0, previous=previous,
    )
    assert estimate.stalled_cycles == 2
    assert estimate.risk > 0.0


def test_failure_and_uncertainty_raise_risk():
    failed = StepResult(
        step=Step(action=ActionType.CLICK, description="click x", params={"find": "x"}),
        status=StepStatus.FAILED, index=1, error="not found",
    )
    calm = _estimator().estimate(_goal(), BeliefState(), [], [], _budget(), 0.0)
    stressed = _estimator().estimate(_goal(), BeliefState(), [], [failed], _budget(), 0.7)
    assert stressed.risk > calm.risk


def test_remaining_work_names_unmet_objectives():
    estimate = _estimator().estimate(
        _goal(), BeliefState(), [], [], _budget(), uncertainty=0.0,
    )
    assert "store page" in estimate.remaining_work
