"""RecoveryManager: hypothesis-ranked recovery, measured outcomes."""
from perceptai.contracts import (
    ActionType,
    HealingPlan,
    Step,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from perceptai.hypothesis import HypothesisGenerator
from perceptai.recovery import RecoveryManager

from tests.conftest import FakeHealer, fast_config


def _manager(healing=None):
    config = fast_config()
    return RecoveryManager(config, FakeHealer(healing), HypothesisGenerator(config))


def _click():
    return Step(action=ActionType.CLICK, description="click submit", params={"find": "Submit"})


def _world():
    return WorldState(windows=[WindowInfo(title="myapp")],
                      elements=[])  # sparse -> loading candidate exists


def test_plan_chooses_most_probable_actionable_hypothesis():
    healing = [HealingPlan(diagnosis="focus moved", failure_type="focus_lost",
                           confidence=0.9,
                           steps=[Step(action=ActionType.FOCUS_WINDOW,
                                       description="refocus", params={"window": "myapp"})])]
    plan = _manager(healing).plan(_click(), "click failed", "view", _world(),
                                  WorldDiff(changed=False), expected_window="myapp")
    assert plan.chosen is not None
    assert plan.chosen.kind == "focus_lost"
    assert plan.steps


def test_plan_keeps_alternatives_alive():
    healing = [HealingPlan(diagnosis="modal blocking", failure_type="modal_dialog",
                           confidence=0.8)]
    plan = _manager(healing).plan(_click(), "not found", "view", _world(),
                                  WorldDiff(changed=False))
    kinds = {h.kind for h in plan.hypotheses}
    assert "modal_dialog" in kinds
    assert len(plan.hypotheses) > 1  # deterministic candidates stayed alive
    assert all(h.status == "open" for h in plan.hypotheses)


def test_rejected_kinds_are_never_chosen_again():
    manager = _manager([HealingPlan(diagnosis="x", failure_type="other", confidence=0.0)])
    plan = manager.plan(_click(), "not found", "view", _world(),
                        WorldDiff(changed=False), rejected_kinds={"loading"})
    assert plan.chosen is None or plan.chosen.kind != "loading"


def test_low_confidence_hypotheses_are_not_acted_on():
    healing = [HealingPlan(diagnosis="maybe focus", failure_type="focus_lost",
                           confidence=0.2,
                           steps=[Step(action=ActionType.FOCUS_WINDOW,
                                       description="refocus", params={"window": "x"})])]
    world = WorldState(windows=[WindowInfo(title="myapp")],
                       elements=[])
    plan = _manager(healing).plan(
        Step(action=ActionType.PRESS, description="press", params={"key": "enter"}),
        "press failed", "view", world, None,
    )
    # loading (0.55) is the only candidate above threshold with steps
    assert plan.chosen is None or plan.chosen.probability > 0.5


def test_assess_confirms_only_measured_recovery():
    manager = _manager([HealingPlan(diagnosis="focus", failure_type="focus_lost",
                                    confidence=0.9,
                                    steps=[Step(action=ActionType.FOCUS_WINDOW,
                                                description="refocus",
                                                params={"window": "m"})])])
    plan = manager.plan(_click(), "click failed", "view", _world(),
                        WorldDiff(changed=False), expected_window="m")

    outcome = manager.assess(plan, 1, all_steps_ok=True, world_changed=True,
                             condition_cleared=True)
    assert outcome.recovered
    assert plan.chosen.status == "confirmed"


def test_assess_rejects_false_recovery():
    """Recovery actions running successfully is NOT recovery when the
    original failure condition still holds."""
    manager = _manager([HealingPlan(diagnosis="loading", failure_type="loading",
                                    confidence=0.9,
                                    steps=[Step(action=ActionType.WAIT,
                                                description="wait", params={"wait": 1.0})])])
    plan = manager.plan(_click(), "Element 'Submit' not found on screen", "view",
                        _world(), WorldDiff(changed=False))

    outcome = manager.assess(plan, 1, all_steps_ok=True, world_changed=False,
                             condition_cleared=False)
    assert not outcome.recovered
    assert plan.chosen.status == "rejected"
    assert "still holds" in plan.chosen.resolution_reason


def test_assess_rejects_failed_recovery_actions():
    manager = _manager([HealingPlan(diagnosis="focus", failure_type="focus_lost",
                                    confidence=0.9,
                                    steps=[Step(action=ActionType.FOCUS_WINDOW,
                                                description="refocus",
                                                params={"window": "m"})])])
    plan = manager.plan(_click(), "click failed", "view", _world(),
                        WorldDiff(changed=False), expected_window="m")
    outcome = manager.assess(plan, 1, all_steps_ok=False, world_changed=False,
                             condition_cleared=True)
    assert not outcome.recovered
    assert plan.chosen.status == "rejected"


def test_healer_crash_degrades_to_signal_hypotheses():
    class CrashingHealer:
        def diagnose(self, *args):
            raise RuntimeError("llm down")

    config = fast_config()
    manager = RecoveryManager(config, CrashingHealer(), HypothesisGenerator(config))
    plan = manager.plan(_click(), "not found", "view", _world(), WorldDiff(changed=False))
    assert plan.hypotheses  # deterministic candidates survive LLM failure
