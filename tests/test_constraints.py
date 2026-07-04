"""ConstraintManager: policy-aware execution, fail-closed for input."""
from perceptai.constraints import ConstraintManager
from perceptai.contracts import (
    ActionType,
    ConstraintVerdict,
    Step,
    WindowInfo,
    WorldState,
)

from tests.conftest import fast_config


def _click(find="Save"):
    return Step(action=ActionType.CLICK, description="click", params={"find": find})


def _world(focused="Trading Terminal - live"):
    return WorldState(windows=[WindowInfo(title=focused, focused=True)],
                      focused_window=focused)


def test_no_constraints_allow_everything():
    manager = ConstraintManager(fast_config())
    assert manager.check_step(_click(), _world()).allowed


def test_blocked_window_denies_input():
    manager = ConstraintManager(fast_config(blocked_window_titles=["trading terminal"]))
    verdict = manager.check_step(_click(), _world())
    assert not verdict.allowed
    assert verdict.constraint == "blocked_windows"
    assert "Trading Terminal" in verdict.reason


def test_blocked_window_allows_observation():
    manager = ConstraintManager(fast_config(blocked_window_titles=["trading terminal"]))
    read = Step(action=ActionType.READ_SCREEN, description="read", params={"find": "totals"})
    assert manager.check_step(read, _world()).allowed


def test_other_windows_unaffected():
    manager = ConstraintManager(fast_config(blocked_window_titles=["trading terminal"]))
    assert manager.check_step(_click(), _world(focused="notepad")).allowed


def test_custom_constraint_registers():
    manager = ConstraintManager(fast_config())

    def no_typing(step, world):
        if step.action == ActionType.TYPE:
            return ConstraintVerdict(allowed=False, reason="typing disabled by org policy")
        return ConstraintVerdict(allowed=True)

    manager.register("no_typing", no_typing)
    typing = Step(action=ActionType.TYPE, description="type", params={"text": "hi"})
    verdict = manager.check_step(typing, _world())
    assert not verdict.allowed
    assert verdict.constraint == "no_typing"
    assert manager.check_step(_click(), _world()).allowed


def test_broken_constraint_fails_closed_for_input_open_for_passive():
    manager = ConstraintManager(fast_config())

    def broken(step, world):
        raise RuntimeError("policy backend down")

    manager.register("broken", broken)
    assert not manager.check_step(_click(), _world()).allowed
    read = Step(action=ActionType.READ_SCREEN, description="read", params={})
    assert manager.check_step(read, _world()).allowed
