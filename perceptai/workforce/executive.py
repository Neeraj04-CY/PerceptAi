"""The Executive Orchestrator — the brain of the workforce.

It understands the mission, plans the work graph, routes orders to
specialists, monitors and reallocates, merges every result into the
shared evidence graph, and produces the final deliverable. It NEVER
performs execution itself: all work happens inside specialists. The
scheduling cycle is deterministic; every decision, dispatch, completion
and merge lands on the canonical event stream with its factors.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Optional, Union

from ..contracts import GoalSpec, TaskContext, TaskReport, VerificationResult
from ..events import EventBus, EventType
from .contracts import (
    Mission,
    MissionDecisionType,
    MissionMetrics,
    MissionResult,
    MissionStatus,
    WorkforceConfig,
    WorkOrder,
    WorkResult,
    WorkStatus,
)
from .evidence_graph import EvidenceGraph
from .graph import WorkGraph
from .planner import MissionPlanner
from .policy import MissionPolicy
from .registry import SpecialistRecord, SpecialistRegistry
from .scheduler import MissionScheduler, RunnerPool
from .specialist import MissionContext


class ExecutiveOrchestrator:
    def __init__(
        self,
        config: WorkforceConfig,
        *,
        registry: SpecialistRegistry,
        planner: MissionPlanner,
        scheduler: MissionScheduler,
        runners: RunnerPool,
        policy: MissionPolicy,
        events: EventBus,
        goal_analyzer,
        reporter,
        memory=None,
        experience=None,
    ):
        self._config = config
        self._registry = registry
        self._planner = planner
        self._scheduler = scheduler
        self._runners = runners
        self._policy = policy
        self._events = events
        self._goals = goal_analyzer
        self._reporter = reporter
        self._memory = memory
        self._experience = experience
        self.id = str(uuid.uuid4())

    # ------------------------------------------------------------- mission

    def run_mission(self, mission: Union[Mission, str]) -> MissionResult:
        if isinstance(mission, str):
            mission = Mission(instruction=mission)
        started = time.time()
        emit = lambda type_, **payload: self._events.emit(  # noqa: E731
            type_, session_id=self.id, task_id=mission.id, **payload)

        emit(EventType.MISSION_STARTED, instruction=mission.instruction,
             workspace=self._policy.workspace.to_dict(),
             specialists=self._registry.snapshot())

        goal = self._understand(mission)
        facts = self._recall(goal)

        orders = self._planner.decompose(
            mission.instruction, goal, self._registry.capabilities(), facts)
        graph = WorkGraph(orders)
        emit(EventType.MISSION_PLANNED,
             orders=[o.to_dict() for o in graph.orders.values()],
             notes=graph.notes)

        ctx = MissionContext(mission=mission, goal=goal, facts=dict(facts),
                             evidence_graph=EvidenceGraph(),
                             memory=self._memory,
                             workspace=self._policy.workspace)

        metrics = MissionMetrics(orders_total=len(graph.orders))
        errors: list[str] = []
        results: dict[str, WorkResult] = {}
        futures: dict[Future, str] = {}
        excluded: dict[str, str] = {}  # order id -> specialist to avoid on retry
        outputs: dict[str, str] = {}
        cycle = 0

        pool = ThreadPoolExecutor(max_workers=max(1, self._config.max_parallel))
        try:
            while True:
                cycle += 1
                self._drain(futures, graph, ctx, results, outputs, metrics, emit,
                            timeout=0)
                self._fail_unroutable(graph, metrics, emit)

                decision = self._scheduler.decide(
                    graph,
                    running=len(futures),
                    elapsed_s=time.time() - started,
                    cost_so_far=metrics.cost_total,
                    cycle=cycle,
                    dispatchable=len(self._dispatchable(graph)),
                )
                emit(EventType.MISSION_DECISION, cycle=cycle,
                     decision=decision.type.value, reason=decision.reason,
                     factors=decision.factors, counts=graph.counts())

                if decision.type == MissionDecisionType.FINISH:
                    break

                if decision.type == MissionDecisionType.ABORT:
                    errors.append(decision.reason)
                    for order in graph.pending():
                        order.status = WorkStatus.CANCELLED
                        order.status_reason = f"mission aborted: {decision.reason}"
                    break

                if decision.type == MissionDecisionType.CANCEL_DUPLICATE:
                    order = graph.get(str(decision.factors.get("cancel", "")))
                    if order is not None:
                        order.status = WorkStatus.CANCELLED
                        order.status_reason = (
                            f"duplicate of {decision.factors.get('keep', '')}")
                        metrics.duplicates_cancelled += 1
                    continue

                if decision.type == MissionDecisionType.REASSIGN:
                    order = graph.get(str(decision.factors.get("order", "")))
                    if order is not None:
                        excluded[order.id] = str(decision.factors.get("exclude", ""))
                        order.status = WorkStatus.PENDING
                        order.status_reason = "reassigned after failure"
                        metrics.reassignments += 1
                    continue

                if decision.type == MissionDecisionType.DISPATCH:
                    self._dispatch(pool, futures, graph, ctx, outputs, excluded,
                                   metrics, emit)
                    metrics.peak_parallelism = max(metrics.peak_parallelism,
                                                   len(futures))
                    continue

                # WAIT: block until a completion (or the poll interval).
                if futures:
                    wait(list(futures), timeout=self._config.wait_poll_s,
                         return_when=FIRST_COMPLETED)
        finally:
            # Never leak running work: let in-flight orders finish and
            # fold their results in before the mission returns.
            pool.shutdown(wait=True)
            self._drain(futures, graph, ctx, results, outputs, metrics, emit,
                        timeout=None)

        metrics.cycles = cycle
        return self._finish(mission, goal, graph, ctx, results, metrics,
                            errors, started, emit)

    # ------------------------------------------------------- understanding

    def _understand(self, mission: Mission) -> GoalSpec:
        try:
            return self._goals.analyze(mission.instruction)
        except Exception:
            return GoalSpec(intent=mission.instruction,
                            objectives=[mission.instruction])

    def _recall(self, goal: GoalSpec) -> dict[str, str]:
        if self._memory is None:
            return {}
        try:
            rows = self._memory.recall_knowledge(goal.entities + goal.required_info)
            return {f"{r['entity']} ({r['attribute']})": str(r["value"])
                    for r in rows}
        except Exception:
            return {}

    # ---------------------------------------------------------- scheduling

    def _dispatchable(self, graph: WorkGraph) -> list[WorkOrder]:
        """Ready orders that could start right now: a healthy candidate
        exists and its resources are actually free."""
        dispatchable = []
        for order in graph.ready():
            candidates = self._registry.candidates(order.capability)
            if any(self._runners.available(c.profile.resources)
                   for c in candidates):
                dispatchable.append(order)
        return dispatchable

    def _fail_unroutable(self, graph: WorkGraph, metrics: MissionMetrics,
                         emit) -> None:
        """An order whose capability no registered specialist provides can
        never run — fail it honestly now and release its dependents."""
        for order in graph.pending():
            if not self._registry.candidates(order.capability):
                if any(order.capability in r.profile.capabilities
                       for r in self._registry.records()):
                    continue  # capability exists, specialists just busy/unhealthy
                order.status = WorkStatus.FAILED
                order.attempts = order.max_attempts
                order.status_reason = (
                    f"no specialist provides capability '{order.capability}'")
                emit(EventType.LOG, message=order.status_reason, order=order.id)
                graph.cascade_failure(order.id)

    def _dispatch(self, pool: ThreadPoolExecutor, futures: dict,
                  graph: WorkGraph, ctx: MissionContext,
                  outputs: dict[str, str], excluded: dict[str, str],
                  metrics: MissionMetrics, emit) -> None:
        for order in self._dispatchable(graph):
            if len(futures) >= self._config.max_parallel:
                break

            verdict = self._policy.check_order(order)
            if not verdict.allowed:
                order.status = WorkStatus.CANCELLED
                order.status_reason = f"policy {verdict.constraint}: {verdict.reason}"
                emit(EventType.LOG, message=order.status_reason, order=order.id)
                graph.cascade_failure(order.id)
                continue

            record = self._scheduler.route(
                order, self._registry.candidates(order.capability),
                success_rate=self._expected_success(order.capability),
                workload_fraction=lambda r: r.workload_fraction(),
                exclude=excluded.get(order.id, ""),
            )
            if record is None:
                continue

            # Seed the order with everything upstream produced for it.
            for key in order.requires:
                if key in outputs and key not in order.inputs:
                    order.inputs[key] = outputs[key]

            order.status = WorkStatus.RUNNING
            order.assigned_to = record.profile.name
            order.attempts += 1
            self._registry.acquire(record.profile.name)
            metrics.specialist_utilization[record.profile.name] = \
                metrics.specialist_utilization.get(record.profile.name, 0) + 1
            emit(EventType.WORK_DISPATCHED, order=order.id,
                 objective=order.objective, capability=order.capability,
                 specialist=record.profile.name, attempt=order.attempts,
                 inputs=len(order.inputs))
            futures[pool.submit(self._run_order, record, order, ctx)] = order.id

    def _expected_success(self, capability: str):
        experience = self._experience

        def rate(record: SpecialistRecord) -> float:
            if experience is not None:
                measured = experience.success_rate(record.profile.name, capability)
                if measured is not None:
                    return measured
            live = record.measured_success_rate()
            return live if live is not None else record.profile.confidence

        return rate

    @staticmethod
    def _run_order(record: SpecialistRecord, order: WorkOrder,
                   ctx: MissionContext) -> WorkResult:
        """Runs on a worker thread. A crashing specialist becomes a FAILED
        result — it never takes the mission down."""
        try:
            return record.specialist.execute(order, ctx)
        except Exception as e:
            return WorkResult(order_id=order.id, specialist=record.profile.name,
                              status=WorkStatus.FAILED, error=str(e))

    def _drain(self, futures: dict, graph: WorkGraph, ctx: MissionContext,
               results: dict[str, WorkResult], outputs: dict[str, str],
               metrics: MissionMetrics, emit,
               timeout: Optional[float]) -> None:
        """Fold finished work into the mission: statuses, shared outputs,
        the evidence graph, registry stats and organizational experience."""
        if not futures:
            return
        done = [f for f in list(futures) if f.done()] if timeout == 0 else \
            list(wait(list(futures), timeout=timeout).done)
        for future in done:
            order_id = futures.pop(future)
            order = graph.get(order_id)
            result: WorkResult = future.result()
            if order is None:
                continue

            self._registry.release(result.specialist, result)
            if self._experience is not None:
                self._experience.record_work(result.specialist, order.capability,
                                             result.ok, result.duration_s)

            order.status = result.status
            order.status_reason = result.error if not result.ok else ""
            results[order_id] = result
            metrics.cost_total += result.cost

            if result.ok:
                outputs.update(result.outputs)
                ctx.facts.update(result.outputs)
                merged = ctx.evidence_graph.ingest(
                    result.evidence,
                    entity=order.entities[0] if order.entities else "")
                if merged:
                    emit(EventType.EVIDENCE_MERGED, order=order_id,
                         merged=merged, graph=ctx.evidence_graph.summary())
            elif order.attempts >= order.max_attempts:
                graph.cascade_failure(order_id)

            emit(EventType.WORK_COMPLETED, order=order_id,
                 specialist=result.specialist, status=result.status.value,
                 summary=result.summary, confidence=result.confidence,
                 duration_s=result.duration_s, cost=result.cost,
                 outputs=list(result.outputs), error=result.error)

    # -------------------------------------------------------------- finish

    def _finish(self, mission: Mission, goal: GoalSpec, graph: WorkGraph,
                ctx: MissionContext, results: dict[str, WorkResult],
                metrics: MissionMetrics, errors: list[str], started: float,
                emit) -> MissionResult:
        orders = list(graph.orders.values())
        counts = graph.counts()
        metrics.orders_completed = counts.get("completed", 0)
        metrics.orders_failed = counts.get("failed", 0)
        metrics.orders_cancelled = counts.get("cancelled", 0)
        metrics.orders_skipped = counts.get("skipped", 0)
        metrics.evidence_count = len(ctx.evidence_graph.current_claims())
        metrics.conflicts_open = len(ctx.evidence_graph.conflicts())

        # Duplicate cancellations were redundant by construction; every
        # other non-completed order is an objective the mission missed.
        effective = [o for o in orders
                     if not (o.status == WorkStatus.CANCELLED
                             and o.status_reason.startswith("duplicate"))]
        completed = [o for o in effective if o.status == WorkStatus.COMPLETED]
        if effective and len(completed) == len(effective) and not errors:
            status = MissionStatus.COMPLETED
        elif completed:
            status = MissionStatus.PARTIAL
        else:
            status = MissionStatus.FAILED

        verification = self._verification(status, ctx, metrics)
        report = self._report(mission, goal, ctx, status, verification, results)

        duration = round(time.time() - started, 2)
        result = MissionResult(
            mission_id=mission.id,
            instruction=mission.instruction,
            status=status,
            report=report,
            goal=goal,
            work=[results[o.id] for o in orders if o.id in results],
            orders=orders,
            metrics=metrics,
            duration_s=duration,
            errors=errors,
            confidence=report.confidence,
            metadata={
                "workspace": self._policy.workspace.to_dict(),
                "evidence_graph": ctx.evidence_graph.summary(),
                "conflicts": ctx.evidence_graph.conflicts(),
                "specialists": self._registry.snapshot(),
                "graph_notes": graph.notes,
            },
        )

        if self._memory is not None:
            ctx.evidence_graph.persist(self._memory, mission.id)
        if self._experience is not None:
            self._experience.record_mission(result)

        emit(EventType.MISSION_COMPLETED, status=status.value,
             duration_s=duration, metrics=metrics.to_dict(),
             report=report.to_dict(), errors=errors)
        return result

    @staticmethod
    def _verification(status: MissionStatus, ctx: MissionContext,
                      metrics: MissionMetrics) -> VerificationResult:
        """Mission-level verification is deterministic: objective coverage
        plus evidence-graph consistency. Conflicts are named, not hidden."""
        summary = ctx.evidence_graph.summary()
        checks_ok = status == MissionStatus.COMPLETED and metrics.conflicts_open == 0
        reasons = [f"{metrics.orders_completed}/{metrics.orders_total} objectives completed"]
        if metrics.conflicts_open:
            reasons.append(f"{metrics.conflicts_open} evidence conflict(s) open")
        return VerificationResult(
            verified=checks_ok,
            confidence=summary["avg_confidence"],
            reason="; ".join(reasons),
        )

    def _report(self, mission: Mission, goal: GoalSpec, ctx: MissionContext,
                status: MissionStatus, verification: VerificationResult,
                results: dict[str, WorkResult]) -> TaskReport:
        """One deliverable through the ONE report builder, grounded in the
        evidence graph only."""
        context = TaskContext(instruction=mission.instruction, goal=goal)
        context.evidence = ctx.evidence_graph.report_evidence()
        context.sources = ctx.evidence_graph.sources()
        artifacts = [a for r in results.values() for a in r.artifacts]
        summary_line = "; ".join(
            f"{r.specialist}: {r.summary}" for r in results.values() if r.summary
        )[:400]
        try:
            # MissionStatus is duck-compatible with TaskStatus here: the
            # builder only reads .value, and "partial" must stay honest.
            return self._reporter.build(goal, context, status, verification,
                                        artifacts, actions_summary=summary_line)
        except Exception:
            return TaskReport(
                executive_summary=(
                    f"Mission {status.value}: {mission.instruction}. "
                    f"{verification.reason}."),
                evidence=list(context.evidence),
                confidence=verification.confidence,
                sources=list(context.sources),
                artifacts=artifacts,
            )
