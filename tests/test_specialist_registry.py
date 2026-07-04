"""SpecialistRegistry: capability lookup, workload, stats, plugin surface."""
from perceptai.simulation import FakeSpecialist
from perceptai.workforce.contracts import WorkResult, WorkStatus
from perceptai.workforce.registry import SpecialistRegistry


def _registry(*specialists):
    registry = SpecialistRegistry()
    for s in specialists:
        registry.register(s)
    return registry


def _result(specialist="s", ok=True, duration=1.0):
    return WorkResult(order_id="o", specialist=specialist,
                      status=WorkStatus.COMPLETED if ok else WorkStatus.FAILED,
                      duration_s=duration, error="" if ok else "boom")


def test_candidates_filter_by_capability():
    registry = _registry(
        FakeSpecialist("alpha", ["research"]),
        FakeSpecialist("beta", ["extraction"]),
    )
    names = [r.profile.name for r in registry.candidates("research")]
    assert names == ["alpha"]
    assert registry.capabilities() == ["research", "extraction"]


def test_busy_specialist_leaves_candidate_pool():
    registry = _registry(FakeSpecialist("alpha", ["research"], max_concurrent=1))
    registry.acquire("alpha")
    assert registry.candidates("research") == []
    registry.release("alpha", _result("alpha"))
    assert len(registry.candidates("research")) == 1


def test_release_records_measured_performance():
    registry = _registry(FakeSpecialist("alpha", ["research"]))
    record = registry.get("alpha")
    assert record.measured_success_rate() is None  # too few samples
    for ok in (True, True, False, True):
        registry.acquire("alpha")
        registry.release("alpha", _result("alpha", ok=ok))
    assert record.completed == 3 and record.failed == 1
    assert record.measured_success_rate() == 0.75
    assert record.last_error == "boom"


def test_unhealthy_specialist_is_excluded():
    class Sick(FakeSpecialist):
        def healthy(self):
            return False

    registry = _registry(Sick("sick", ["research"]),
                         FakeSpecialist("well", ["research"]))
    names = [r.profile.name for r in registry.candidates("research")]
    assert names == ["well"]


def test_registration_requires_no_runtime_changes():
    """A brand-new capability becomes routable the moment its specialist
    registers — the plugin contract."""
    registry = _registry()
    assert registry.candidates("sap_export") == []
    registry.register(FakeSpecialist("sap", ["sap_export"]))
    assert [r.profile.name for r in registry.candidates("sap_export")] == ["sap"]


def test_snapshot_is_operational_data():
    registry = _registry(FakeSpecialist("alpha", ["research"]))
    registry.acquire("alpha")
    snap = registry.snapshot()
    assert snap[0]["name"] == "alpha"
    assert snap[0]["active"] == 1
    assert snap[0]["healthy"] is True
