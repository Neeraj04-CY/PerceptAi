"""ExecutiveOrchestrator: end-to-end simulated missions.

The Executive manages — plans, routes, merges, reports — and never
executes work itself. All scenarios run the real workforce layer against
FakeSpecialists and a scripted decomposition: no LLM, no screen.
"""
from perceptai.events import EventType
from perceptai.simulation import FakeSpecialist, build_simulated_workforce
from perceptai.workforce.contracts import (
    MissionStatus,
    WorkOrder,
    WorkStatus,
)
from perceptai.workforce.policy import MissionPolicy, WorkforceLimits


def _order(objective, capability="research", **kwargs):
    return WorkOrder(objective=objective, capability=capability, **kwargs)


def _events_of(events, type_):
    return [e for e in events if e.type == type_]


def test_mission_completes_with_grounded_report_and_events():
    specialist = FakeSpecialist("researcher", ["research"], script={
        "pricing": {"evidence": [("pricing", "2.9% + 30c", "stripe.com", 0.8)]},
        "api": {"evidence": [("api_style", "REST", "docs.stripe.com", 0.9)]},
    }, max_concurrent=2)
    workforce, events = build_simulated_workforce(
        orders=[_order("find stripe pricing", produces=["pricing"]),
                _order("find stripe api style", produces=["api_style"])],
        specialists=[specialist],
    )
    result = workforce.run_mission("Research Stripe")

    assert result.status == MissionStatus.COMPLETED
    assert result.metrics.orders_completed == 2
    assert len(specialist.executed) == 2
    # The report is composed from the shared evidence graph only.
    values = {e.value for e in result.report.evidence}
    assert values == {"2.9% + 30c", "REST"}
    assert "stripe.com" in result.report.sources
    for type_ in (EventType.MISSION_STARTED, EventType.MISSION_PLANNED,
                  EventType.MISSION_DECISION, EventType.WORK_DISPATCHED,
                  EventType.WORK_COMPLETED, EventType.EVIDENCE_MERGED,
                  EventType.MISSION_COMPLETED):
        assert _events_of(events, type_), f"missing {type_.value}"


def test_outputs_flow_to_dependent_orders():
    producer = FakeSpecialist("producer", ["research"], script={
        "find": {"outputs": {"pricing": "2.9%"}},
    })
    consumer = FakeSpecialist("consumer", ["reporting"])
    workforce, _events = build_simulated_workforce(
        orders=[_order("find pricing", produces=["pricing"]),
                _order("summarize pricing", capability="reporting",
                       requires=["pricing"])],
        specialists=[producer, consumer],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.COMPLETED
    # The dependent order was seeded with the upstream output.
    assert consumer.executed[0].inputs == {"pricing": "2.9%"}


def test_failure_is_reassigned_to_alternate_specialist():
    flaky = FakeSpecialist("flaky", ["research"], fail_all=True, cost=0.5)
    solid = FakeSpecialist("solid", ["research"], cost=5.0)
    workforce, _events = build_simulated_workforce(
        orders=[_order("research")],
        specialists=[flaky, solid],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.COMPLETED
    assert result.metrics.reassignments == 1
    assert len(flaky.executed) == 1 and len(solid.executed) == 1
    assert result.orders[0].assigned_to == "solid"


def test_permanent_failure_cascades_and_status_is_honest():
    broken = FakeSpecialist("broken", ["research"], fail_all=True)
    reporter = FakeSpecialist("reporter", ["reporting"])
    workforce, _events = build_simulated_workforce(
        orders=[_order("find data", produces=["data"]),
                _order("report on data", capability="reporting",
                       requires=["data"])],
        specialists=[broken, reporter],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.FAILED
    statuses = {o.objective: o.status for o in result.orders}
    assert statuses["find data"] == WorkStatus.FAILED
    assert statuses["report on data"] == WorkStatus.SKIPPED
    assert len(reporter.executed) == 0  # skipped work never ran


def test_policy_denial_cancels_not_fails():
    workforce, _events = build_simulated_workforce(
        orders=[_order("research"), _order("automate", capability="desktop")],
        specialists=[FakeSpecialist("r", ["research"]),
                     FakeSpecialist("d", ["desktop"])],
        policy=MissionPolicy(
            limits=WorkforceLimits(allowed_capabilities=["research"])),
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.PARTIAL
    denied = next(o for o in result.orders if o.capability == "desktop")
    assert denied.status == WorkStatus.CANCELLED
    assert "capability_allowlist" in denied.status_reason


def test_duplicate_work_is_cancelled_before_running():
    specialist = FakeSpecialist("r", ["research"], max_concurrent=2)
    workforce, _events = build_simulated_workforce(
        orders=[_order("research stripe pricing", produces=["pricing"],
                       entities=["Stripe"], priority=1),
                _order("look up stripe pricing", produces=["pricing"],
                       entities=["Stripe"], priority=5)],
        specialists=[specialist],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.COMPLETED
    assert result.metrics.duplicates_cancelled == 1
    assert len(specialist.executed) == 1  # the duplicate never ran


def test_missing_capability_fails_honestly():
    workforce, _events = build_simulated_workforce(
        orders=[_order("teleport", capability="quantum")],
        specialists=[FakeSpecialist("r", ["research"])],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.FAILED
    assert "no specialist provides capability" in result.orders[0].status_reason


def test_independent_work_runs_in_parallel():
    fast = FakeSpecialist("fast", ["research"], latency_s=0.05, max_concurrent=4)
    workforce, _events = build_simulated_workforce(
        orders=[_order(f"objective {i}", produces=[f"k{i}"]) for i in range(3)],
        specialists=[fast],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.COMPLETED
    assert result.metrics.peak_parallelism >= 2


def test_single_worker_serializes_via_workload():
    solo = FakeSpecialist("solo", ["research"], latency_s=0.02, max_concurrent=1)
    workforce, _events = build_simulated_workforce(
        orders=[_order("a", produces=["ka"]), _order("b", produces=["kb"])],
        specialists=[solo],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.COMPLETED
    assert result.metrics.peak_parallelism == 1
    assert len(solo.executed) == 2


def test_evidence_conflicts_survive_into_the_result():
    a = FakeSpecialist("a", ["research"], script={
        "one": {"evidence": [("pricing", "2.9%", "site-a", 0.8)]},
    })
    b = FakeSpecialist("b", ["browser"], script={
        "two": {"evidence": [("pricing", "3.4%", "site-b", 0.8)]},
    })
    workforce, _events = build_simulated_workforce(
        orders=[_order("source one", entities=["Stripe"], produces=["p1"]),
                _order("source two", capability="browser",
                       entities=["Stripe"], produces=["p2"])],
        specialists=[a, b],
    )
    result = workforce.run_mission("mission")
    assert result.metrics.conflicts_open == 1
    assert result.metadata["conflicts"][0]["attribute"] == "pricing"
    # Work completed, but the disagreement stays visible in the summary.
    assert result.status == MissionStatus.COMPLETED
    assert result.metadata["evidence_graph"]["conflicts"] == 1


def test_crashing_specialist_becomes_failed_result_not_crash():
    class Crasher(FakeSpecialist):
        def execute(self, order, ctx):
            raise RuntimeError("kaboom")

    workforce, _events = build_simulated_workforce(
        orders=[_order("explode", max_attempts=1)],
        specialists=[Crasher("crash", ["research"])],
    )
    result = workforce.run_mission("mission")
    assert result.status == MissionStatus.FAILED
    assert "kaboom" in result.orders[0].status_reason


def test_scheduling_is_deterministic():
    """Identical mission, identical specialists -> identical decision and
    dispatch sequences (with serialized execution)."""

    def run():
        specialist = FakeSpecialist("r", ["research", "reporting"])
        workforce, events = build_simulated_workforce(
            orders=[_order("a", produces=["ka"], priority=2),
                    _order("b", produces=["kb"], priority=1),
                    _order("c", capability="reporting", requires=["ka", "kb"])],
            specialists=[specialist],
        )
        workforce.run_mission("mission")
        # Order ids are random (objectives identify dispatches stably) and
        # WAIT counts are wall-clock timing — every allocating decision
        # must be identical.
        trace = []
        for e in events:
            if e.type == EventType.MISSION_DECISION and \
                    e.payload.get("decision") != "wait":
                trace.append((e.payload["decision"], None))
            elif e.type == EventType.WORK_DISPATCHED:
                trace.append(("dispatched", e.payload.get("objective")))
        return trace

    assert run() == run()
