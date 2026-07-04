"""Runner pool and the mission scheduler.

RunnerPool models physical execution surfaces. One runner = one desktop
= ONE AgentSession, so every specialist on that runner shares the same
world model, memory and perception — nothing is perceived twice. Desktop
work serializes honestly on an exclusive lease; compute work needs no
lease at all. A fleet of remote runners is more entries in the pool,
not a redesign.

MissionScheduler is pure: given the graph and the mission's budget
state it returns exactly one typed MissionDecision per cycle, and its
routing score is a deterministic function of measured performance,
cost and workload. Side effects live in the Executive.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from .contracts import (
    MissionDecision,
    MissionDecisionType,
    WorkforceConfig,
    WorkOrder,
)
from .graph import WorkGraph


class RunnerPool:
    def __init__(self, session_factory: Callable[[], Any],
                 runner_names: tuple[str, ...] = ("local",)):
        self._factory = session_factory
        self._runners: dict[str, dict] = {
            name: {"lock": threading.Lock(), "session": None}
            for name in runner_names
        }

    def _session_for(self, runner: dict) -> Any:
        if runner["session"] is None:
            runner["session"] = self._factory()
        return runner["session"]

    def available(self, resources: list[str]) -> bool:
        """Non-blocking capacity check for scheduling decisions."""
        if "desktop" not in resources:
            return True
        for runner in self._runners.values():
            if not runner["lock"].locked():
                return True
        return False

    @contextmanager
    def lease(self, resources: list[str]) -> Iterator[Any]:
        """Exclusive session lease for desktop work; compute work gets no
        session (and must not want one). Blocks until a runner frees up —
        capacity was already checked at dispatch time."""
        if "desktop" not in resources:
            yield None
            return
        names = sorted(self._runners)
        while True:
            for name in names:
                runner = self._runners[name]
                if runner["lock"].acquire(blocking=False):
                    try:
                        yield self._session_for(runner)
                    finally:
                        runner["lock"].release()
                    return
            # Every runner busy: block on the first one deterministically.
            runner = self._runners[names[0]]
            runner["lock"].acquire()
            try:
                yield self._session_for(runner)
            finally:
                runner["lock"].release()
            return


class MissionScheduler:
    def __init__(self, config: WorkforceConfig):
        self._config = config

    # ------------------------------------------------------------ deciding

    def decide(self, graph: WorkGraph, *, running: int, elapsed_s: float,
               cost_so_far: float, cycle: int,
               dispatchable: int) -> MissionDecision:
        """One typed decision per scheduling cycle, exhausted budgets and
        finished graphs first — mirrors the runtime's decision engine."""
        if graph.done():
            return MissionDecision(
                type=MissionDecisionType.FINISH,
                reason="all work orders reached a terminal state",
                factors={"counts": graph.counts()},
            )
        if cycle >= self._config.max_mission_cycles:
            return MissionDecision(
                type=MissionDecisionType.ABORT,
                reason=f"mission cycle budget exhausted ({cycle})",
                factors={"budget": "cycles"},
            )
        if elapsed_s >= self._config.max_mission_duration_s:
            return MissionDecision(
                type=MissionDecisionType.ABORT,
                reason=f"mission time budget exhausted ({elapsed_s:.0f}s)",
                factors={"budget": "time"},
            )
        if cost_so_far >= self._config.max_total_cost:
            return MissionDecision(
                type=MissionDecisionType.ABORT,
                reason=f"mission cost budget exhausted ({cost_so_far:.1f})",
                factors={"budget": "cost"},
            )

        duplicate_pairs = graph.duplicates()
        if duplicate_pairs:
            keep, cancel = duplicate_pairs[0]
            return MissionDecision(
                type=MissionDecisionType.CANCEL_DUPLICATE,
                reason=f"order {cancel.id} duplicates {keep.id} "
                       f"(same capability, outputs and entities)",
                factors={"keep": keep.id, "cancel": cancel.id},
            )

        retryable = self._retryable(graph)
        if retryable is not None:
            return MissionDecision(
                type=MissionDecisionType.REASSIGN,
                reason=f"order {retryable.id} failed on '{retryable.assigned_to}' "
                       f"with attempts remaining",
                factors={"order": retryable.id,
                         "attempts": retryable.attempts,
                         "exclude": retryable.assigned_to},
            )

        if dispatchable > 0 and running < self._config.max_parallel:
            return MissionDecision(
                type=MissionDecisionType.DISPATCH,
                reason=f"{dispatchable} order(s) ready with capacity for "
                       f"{self._config.max_parallel - running} more",
                factors={"ready": dispatchable, "running": running},
            )

        if running > 0:
            return MissionDecision(
                type=MissionDecisionType.WAIT,
                reason=f"{running} order(s) in flight; waiting for a completion",
                factors={"running": running},
            )

        if graph.stalled():
            released = graph.resolve_stall()
            if released:
                return MissionDecision(
                    type=MissionDecisionType.WAIT,
                    reason=f"cascade released {len(released)} orphaned order(s)",
                    factors={"skipped": [o.id for o in released]},
                )
            return MissionDecision(
                type=MissionDecisionType.ABORT,
                reason="deadlock: pending work with unsatisfiable dependencies",
                factors={"deadlock": True, "pending": [o.id for o in graph.pending()]},
            )

        # Ready work exists but nothing can run (no capacity was handled
        # above, so this is resource starvation): wait for a lease.
        return MissionDecision(
            type=MissionDecisionType.WAIT,
            reason="ready work is waiting for an execution resource",
            factors={"ready": dispatchable},
        )

    @staticmethod
    def _retryable(graph: WorkGraph) -> Optional[WorkOrder]:
        candidates = [
            o for o in graph.orders.values()
            if o.status.value == "failed" and o.attempts < o.max_attempts
        ]
        return min(candidates, key=lambda o: (o.priority, o.id)) if candidates else None

    # ------------------------------------------------------------- routing

    @staticmethod
    def route(order: WorkOrder, candidates: list, *,
              success_rate: Callable[[Any], float],
              workload_fraction: Callable[[Any], float],
              exclude: str = "") -> Optional[Any]:
        """Pick the best specialist record for an order. Deterministic:
        measured success first, then cost and current workload, name as
        the final tiebreak. Never hardcoded to any specialist."""
        viable = [c for c in candidates if c.profile.name != exclude]
        if not viable:
            viable = list(candidates)  # nowhere else to go: retry in place
        if not viable:
            return None
        max_cost = max(c.profile.cost for c in viable) or 1.0

        def score(record) -> tuple:
            fitness = (
                0.6 * success_rate(record)
                + 0.2 * (1.0 - record.profile.cost / max_cost)
                + 0.2 * (1.0 - workload_fraction(record))
            )
            return (-round(fitness, 6), record.profile.name)

        return sorted(viable, key=score)[0]
