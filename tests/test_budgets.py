"""ExecutionBudgetManager: one ledger, honest pressure."""
import time

from perceptai.budgets import ExecutionBudgetManager
from perceptai.contracts import ExecutionState

from tests.conftest import fast_config


def _manager(**config_overrides):
    return ExecutionBudgetManager(fast_config(**config_overrides))


def test_snapshot_reflects_state():
    manager = _manager(max_steps=10)
    state = ExecutionState(steps_executed=4, replans=1, healings=2, vision_escalations=1)
    snap = manager.snapshot(state, time.time() - 3, llm_calls=5, vision_calls=1)
    assert snap.steps_used == 4 and snap.steps_max == 10
    assert snap.replans_used == 1
    assert snap.recoveries_used == 2
    assert snap.llm_calls_used == 5
    assert snap.vision_calls_used == 1
    assert snap.elapsed_s >= 3


def test_pressure_is_tightest_budget():
    manager = _manager(max_steps=10, max_replans=4)
    state = ExecutionState(steps_executed=2, replans=4)  # replans exhausted
    snap = manager.snapshot(state, time.time(), 0, 0)
    assert snap.pressure == 1.0


def test_affordability_checks():
    manager = _manager(max_steps=2, max_replans=1, max_recovery_total=1,
                       max_vision_escalations=1)
    state = ExecutionState(steps_executed=2, replans=1, healings=1, vision_escalations=1)
    snap = manager.snapshot(state, time.time(), 0, 1)
    assert not manager.can_step(snap)
    assert not manager.can_replan(snap)
    assert not manager.can_recover(snap)
    assert not manager.can_escalate_vision(snap)


def test_time_budget():
    manager = _manager(max_task_duration_s=1.0)
    snap = manager.snapshot(ExecutionState(), time.time() - 2, 0, 0)
    assert manager.time_exceeded(snap)
    assert not manager.can_step(snap)


def test_fresh_run_has_no_pressure():
    snap = _manager().snapshot(ExecutionState(), time.time(), 0, 0)
    assert snap.pressure < 0.05
    assert _manager().can_step(snap)
