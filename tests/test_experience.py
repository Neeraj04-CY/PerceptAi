"""ExperienceStore: missions permanently improve routing."""
from perceptai.workforce.contracts import (
    MissionMetrics,
    MissionResult,
    MissionStatus,
)
from perceptai.workforce.experience import ExperienceStore


def _store(tmp_path):
    return ExperienceStore(tmp_path / "experience.db")


def test_work_stats_accumulate_and_gate_on_samples(tmp_path):
    store = _store(tmp_path)
    assert store.success_rate("alpha", "research") is None
    store.record_work("alpha", "research", ok=True, duration_s=10)
    store.record_work("alpha", "research", ok=True, duration_s=12)
    # Two samples: still not statistically meaningful.
    assert store.success_rate("alpha", "research") is None
    store.record_work("alpha", "research", ok=False, duration_s=30)
    assert store.success_rate("alpha", "research") == 2 / 3


def test_rates_are_scoped_per_capability(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        store.record_work("alpha", "research", ok=True, duration_s=1)
        store.record_work("alpha", "extraction", ok=False, duration_s=1)
    assert store.success_rate("alpha", "research") == 1.0
    assert store.success_rate("alpha", "extraction") == 0.0


def test_mission_history_is_recorded(tmp_path):
    store = _store(tmp_path)
    result = MissionResult(
        mission_id="m1", instruction="research stripe",
        status=MissionStatus.COMPLETED, duration_s=42.0,
        metrics=MissionMetrics(orders_total=3, orders_completed=3,
                               cost_total=6.5),
    )
    store.record_mission(result)
    history = store.mission_history()
    assert len(history) == 1
    assert history[0]["id"] == "m1"
    assert history[0]["status"] == "completed"
    assert history[0]["orders_completed"] == 3


def test_persistence_survives_reopen(tmp_path):
    _store(tmp_path).record_work("alpha", "research", ok=True, duration_s=1)
    reopened = _store(tmp_path)
    # One sample is below the significance gate but must be on disk.
    assert reopened.success_rate("alpha", "research", min_samples=1) == 1.0
