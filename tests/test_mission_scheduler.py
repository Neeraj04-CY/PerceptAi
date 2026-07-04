"""MissionScheduler: one typed decision per cycle, deterministic routing;
RunnerPool: honest resource leases."""
from perceptai.simulation import FakeSpecialist
from perceptai.workforce.contracts import (
    MissionDecisionType,
    WorkforceConfig,
    WorkOrder,
    WorkStatus,
)
from perceptai.workforce.graph import WorkGraph
from perceptai.workforce.registry import SpecialistRegistry
from perceptai.workforce.scheduler import MissionScheduler, RunnerPool

from tests.conftest import fast_config


def _scheduler(**cfg):
    return MissionScheduler(WorkforceConfig(engine=fast_config(), **cfg))


def _decide(scheduler, graph, running=0, elapsed=0.0, cost=0.0, cycle=1,
            dispatchable=None):
    if dispatchable is None:
        dispatchable = len(graph.ready())
    return scheduler.decide(graph, running=running, elapsed_s=elapsed,
                            cost_so_far=cost, cycle=cycle,
                            dispatchable=dispatchable)


def _order(objective, **kwargs):
    kwargs.setdefault("capability", "research")
    return WorkOrder(objective=objective, **kwargs)


def test_finish_when_all_terminal():
    graph = WorkGraph([_order("a")])
    graph.orders[list(graph.orders)[0]].status = WorkStatus.COMPLETED
    assert _decide(_scheduler(), graph).type == MissionDecisionType.FINISH


def test_budget_exhaustion_aborts_with_budget_named():
    graph = WorkGraph([_order("a")])
    scheduler = _scheduler(max_mission_cycles=5)
    decision = _decide(scheduler, graph, cycle=5)
    assert decision.type == MissionDecisionType.ABORT
    assert decision.factors["budget"] == "cycles"
    decision = _decide(_scheduler(max_total_cost=10.0), graph, cost=10.0)
    assert decision.factors["budget"] == "cost"
    decision = _decide(_scheduler(max_mission_duration_s=60.0), graph, elapsed=61.0)
    assert decision.factors["budget"] == "time"


def test_duplicate_cancellation_precedes_dispatch():
    keep = _order("research stripe", produces=["pricing"], entities=["Stripe"],
                  priority=1)
    dupe = _order("stripe research again", produces=["pricing"],
                  entities=["Stripe"], priority=5)
    graph = WorkGraph([keep, dupe])
    decision = _decide(_scheduler(), graph)
    assert decision.type == MissionDecisionType.CANCEL_DUPLICATE
    assert decision.factors == {"keep": keep.id, "cancel": dupe.id}


def test_failed_order_with_attempts_left_is_reassigned():
    order = _order("a")
    graph = WorkGraph([order])
    order.status = WorkStatus.FAILED
    order.attempts = 1
    order.assigned_to = "alpha"
    decision = _decide(_scheduler(), graph)
    assert decision.type == MissionDecisionType.REASSIGN
    assert decision.factors["exclude"] == "alpha"


def test_exhausted_attempts_do_not_reassign():
    order = _order("a")
    graph = WorkGraph([order])
    order.status = WorkStatus.FAILED
    order.attempts = order.max_attempts
    # Terminal failure, nothing else pending -> FINISH.
    assert _decide(_scheduler(), graph).type == MissionDecisionType.FINISH


def test_dispatch_respects_parallel_capacity():
    graph = WorkGraph([_order("a"), _order("b")])
    scheduler = _scheduler(max_parallel=1)
    assert _decide(scheduler, graph, running=0).type == MissionDecisionType.DISPATCH
    assert _decide(scheduler, graph, running=1).type == MissionDecisionType.WAIT


def test_deadlock_aborts_after_cascade_cannot_release():
    order = _order("a")
    graph = WorkGraph([order])
    order.depends_on = ["ghost"]  # unsatisfiable by construction
    decision = _decide(_scheduler(), graph, dispatchable=0)
    assert decision.type == MissionDecisionType.ABORT
    assert decision.factors.get("deadlock") is True


def test_routing_prefers_measured_success_then_cost_then_name():
    registry = SpecialistRegistry()
    registry.register(FakeSpecialist("expensive", ["research"], cost=5.0))
    registry.register(FakeSpecialist("cheap", ["research"], cost=1.0))
    order = _order("a")
    chosen = MissionScheduler.route(
        order, registry.candidates("research"),
        success_rate=lambda r: 0.8,
        workload_fraction=lambda r: 0.0,
    )
    assert chosen.profile.name == "cheap"
    # Higher measured success outweighs cost.
    chosen = MissionScheduler.route(
        order, registry.candidates("research"),
        success_rate=lambda r: 0.95 if r.profile.name == "expensive" else 0.5,
        workload_fraction=lambda r: 0.0,
    )
    assert chosen.profile.name == "expensive"


def test_routing_excludes_failed_specialist_when_alternatives_exist():
    registry = SpecialistRegistry()
    registry.register(FakeSpecialist("alpha", ["research"]))
    registry.register(FakeSpecialist("beta", ["research"]))
    chosen = MissionScheduler.route(
        _order("a"), registry.candidates("research"),
        success_rate=lambda r: 0.8, workload_fraction=lambda r: 0.0,
        exclude="alpha",
    )
    assert chosen.profile.name == "beta"
    # Sole candidate: retry in place rather than nowhere.
    solo = SpecialistRegistry()
    solo.register(FakeSpecialist("alpha", ["research"]))
    chosen = MissionScheduler.route(
        _order("a"), solo.candidates("research"),
        success_rate=lambda r: 0.8, workload_fraction=lambda r: 0.0,
        exclude="alpha",
    )
    assert chosen.profile.name == "alpha"


def test_runner_pool_leases_desktop_exclusively():
    pool = RunnerPool(lambda: object())
    assert pool.available(["desktop"])
    with pool.lease(["desktop"]) as session:
        assert session is not None
        assert not pool.available(["desktop"])
        # Compute work needs no lease even while the desktop is busy.
        with pool.lease([]) as compute_session:
            assert compute_session is None
    assert pool.available(["desktop"])


def test_runner_pool_shares_one_session_per_runner():
    created = []

    def factory():
        created.append(object())
        return created[-1]

    pool = RunnerPool(factory)
    with pool.lease(["desktop"]) as first:
        pass
    with pool.lease(["desktop"]) as second:
        pass
    assert first is second and len(created) == 1
