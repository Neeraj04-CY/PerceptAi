"""DecisionEngine: ordered rules, budget awareness, uncertainty behavior."""
from perceptai.budgets import ExecutionBudgetManager
from perceptai.contracts import (
    BudgetSnapshot,
    DecisionType,
    GoalSpec,
    ProgressEstimate,
    StrategyProfile,
)
from perceptai.decision import DecisionEngine, DecisionInputs

from tests.conftest import fast_config


def _budget(**overrides):
    defaults = dict(
        steps_used=1, steps_max=12, replans_used=0, replans_max=4,
        recoveries_used=0, recoveries_max=6, llm_calls_used=2, llm_calls_max=60,
        vision_calls_used=0, vision_calls_max=3, elapsed_s=5.0, time_max_s=600.0,
    )
    defaults.update(overrides)
    return BudgetSnapshot(**defaults)


def _inputs(**overrides):
    defaults = dict(
        budget=_budget(),
        strategy=StrategyProfile(name="test", verify_step_interval=3,
                                 uncertainty_tolerance=0.65),
        progress=ProgressEstimate(),
        uncertainty=0.0,
        queue_len=2,
        executed_count=1,
        steps_since_verification=1,
        steps_since_observation=1,
    )
    defaults.update(overrides)
    return DecisionInputs(**defaults)


def _engine():
    config = fast_config()
    return DecisionEngine(config, ExecutionBudgetManager(config))


def test_calm_state_continues():
    decision = _engine().decide(_inputs())
    assert decision.type == DecisionType.CONTINUE
    assert "uncertainty" in decision.factors  # explainable


def test_constraint_abort_outranks_everything():
    decision = _engine().decide(_inputs(constraint_abort="policy violated", failure_pending=True))
    assert decision.type == DecisionType.ABORT


def test_time_exhaustion_aborts():
    decision = _engine().decide(_inputs(budget=_budget(elapsed_s=601.0)))
    assert decision.type == DecisionType.ABORT


def test_fresh_failure_recovers_first():
    decision = _engine().decide(_inputs(failure_pending=True))
    assert decision.type == DecisionType.RECOVER


def test_failed_recovery_escalates_to_replan():
    decision = _engine().decide(_inputs(failure_pending=True, recovery_attempted_for_failure=True))
    assert decision.type == DecisionType.REPLAN


def test_exhausted_budgets_abort_on_failure():
    decision = _engine().decide(_inputs(
        failure_pending=True, recovery_attempted_for_failure=True,
        budget=_budget(replans_used=4),
    ))
    assert decision.type == DecisionType.ABORT


def test_constraint_failure_replans_not_recovers():
    decision = _engine().decide(_inputs(failure_pending=True, failure_is_constraint=True))
    assert decision.type == DecisionType.REPLAN


def test_constraint_failure_without_replan_budget_needs_user():
    decision = _engine().decide(_inputs(
        failure_pending=True, failure_is_constraint=True, budget=_budget(replans_used=4),
    ))
    assert decision.type == DecisionType.NEED_USER


def test_goal_achieved_finishes():
    decision = _engine().decide(_inputs(goal_achieved_signal=True))
    assert decision.type == DecisionType.FINISH


def test_step_budget_exhaustion_finishes():
    decision = _engine().decide(_inputs(budget=_budget(steps_used=12)))
    assert decision.type == DecisionType.FINISH


def test_post_launch_triggers_replan():
    decision = _engine().decide(_inputs(post_launch_replan_pending=True))
    assert decision.type == DecisionType.REPLAN


def test_empty_queue_finishes_without_criteria():
    decision = _engine().decide(_inputs(queue_len=0))
    assert decision.type == DecisionType.FINISH


def test_empty_queue_replans_when_goal_has_criteria():
    goal = GoalSpec(intent="x", completion_criteria=["report delivered"])
    decision = _engine().decide(_inputs(queue_len=0, goal=goal))
    assert decision.type == DecisionType.REPLAN


def test_high_uncertainty_observes_before_acting():
    decision = _engine().decide(_inputs(uncertainty=0.8))
    assert decision.type == DecisionType.OBSERVE


def test_perception_gap_escalates_when_affordable():
    decision = _engine().decide(_inputs(uncertainty=0.8, perception_gap=True))
    assert decision.type == DecisionType.ESCALATE_PERCEPTION


def test_reluctant_strategy_never_escalates():
    strategy = StrategyProfile(name="nav", perception_escalation="reluctant",
                               uncertainty_tolerance=0.65)
    decision = _engine().decide(_inputs(uncertainty=0.8, perception_gap=True, strategy=strategy))
    assert decision.type == DecisionType.OBSERVE


def test_vision_budget_exhaustion_falls_back_to_observe():
    decision = _engine().decide(_inputs(
        uncertainty=0.8, perception_gap=True, budget=_budget(vision_calls_used=3),
    ))
    assert decision.type == DecisionType.OBSERVE


def test_observation_loop_is_capped():
    decision = _engine().decide(_inputs(uncertainty=0.9, consecutive_observations=2))
    assert decision.type != DecisionType.OBSERVE


def test_verification_due_after_interval():
    decision = _engine().decide(_inputs(steps_since_verification=3))
    assert decision.type == DecisionType.VERIFY


def test_uncertainty_shortens_verification_interval():
    # interval 3 at uncertainty 0 -> ~2 at uncertainty 0.6 (below the
    # observe tolerance, so verification is the response).
    decision = _engine().decide(_inputs(uncertainty=0.6, steps_since_verification=2))
    assert decision.type == DecisionType.VERIFY


def test_decisions_carry_reasons():
    for inputs, expected in [
        (_inputs(failure_pending=True), DecisionType.RECOVER),
        (_inputs(queue_len=0), DecisionType.FINISH),
    ]:
        decision = _engine().decide(inputs)
        assert decision.type == expected
        assert decision.reason
        assert decision.factors["budget_pressure"] >= 0.0
