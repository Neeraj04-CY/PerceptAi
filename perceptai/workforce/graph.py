"""The work graph: the mission's dependency structure.

Edges come from data (an order that requires a key depends on every
order that produces it) plus explicit depends_on ids. The Executive
schedules from this graph — ready-set, duplicate detection, failure
cascade and stall detection are all deterministic computations here.
"""
from __future__ import annotations

from typing import Optional

from .contracts import WorkOrder, WorkStatus

TERMINAL = (WorkStatus.COMPLETED, WorkStatus.FAILED,
            WorkStatus.CANCELLED, WorkStatus.SKIPPED)


class WorkGraph:
    def __init__(self, orders: list[WorkOrder]):
        self.orders: dict[str, WorkOrder] = {o.id: o for o in orders}
        self.notes: list[str] = []
        self._derive_edges()
        self._break_cycles()

    # ------------------------------------------------------------ building

    def _derive_edges(self) -> None:
        producers: dict[str, list[str]] = {}
        for order in self.orders.values():
            for key in order.produces:
                producers.setdefault(key, []).append(order.id)
        for order in self.orders.values():
            # Unknown explicit ids are planner noise, not edges.
            valid = [d for d in order.depends_on if d in self.orders and d != order.id]
            dropped = set(order.depends_on) - set(valid)
            if dropped:
                self.notes.append(
                    f"order {order.id}: dropped unknown dependencies {sorted(dropped)}")
            deps = set(valid)
            for key in order.requires:
                for producer in producers.get(key, []):
                    if producer != order.id:
                        deps.add(producer)
            order.depends_on = sorted(deps)

    def _break_cycles(self) -> None:
        """Deterministic cycle breaking: drop the back edge found on the
        DFS path (lowest-id order first) and record what was dropped."""
        state: dict[str, int] = {}  # 0 unvisited, 1 on path, 2 done

        def visit(order_id: str, path: list[str]) -> None:
            state[order_id] = 1
            path.append(order_id)
            order = self.orders[order_id]
            for dep in list(order.depends_on):
                if state.get(dep, 0) == 1:
                    order.depends_on.remove(dep)
                    self.notes.append(
                        f"order {order_id}: dropped cyclic dependency on {dep}")
                elif state.get(dep, 0) == 0:
                    visit(dep, path)
            path.pop()
            state[order_id] = 2

        for order_id in sorted(self.orders):
            if state.get(order_id, 0) == 0:
                visit(order_id, [])

    # ---------------------------------------------------------- scheduling

    def ready(self) -> list[WorkOrder]:
        """Pending orders whose every dependency completed, best first."""
        ready = [
            o for o in self.orders.values()
            if o.status == WorkStatus.PENDING and all(
                d in self.orders
                and self.orders[d].status == WorkStatus.COMPLETED
                for d in o.depends_on
            )
        ]
        # Tie-break on objective, not id: ids are random, and identical
        # missions must dispatch in identical order.
        return sorted(ready, key=lambda o: (o.priority, o.objective, o.id))

    def running(self) -> list[WorkOrder]:
        return [o for o in self.orders.values() if o.status == WorkStatus.RUNNING]

    def pending(self) -> list[WorkOrder]:
        return [o for o in self.orders.values() if o.status == WorkStatus.PENDING]

    def done(self) -> bool:
        """Every order terminal — a failed order with attempts remaining
        is not: it is still the scheduler's to reassign."""
        for order in self.orders.values():
            if order.status not in TERMINAL:
                return False
            if order.status == WorkStatus.FAILED and \
                    order.attempts < order.max_attempts:
                return False
        return True

    def stalled(self) -> bool:
        """Nothing ready, nothing running, but work remains: a deadlock
        unless the cascade can release it."""
        return bool(self.pending()) and not self.ready() and not self.running()

    def duplicates(self) -> list[tuple[WorkOrder, WorkOrder]]:
        """Pending orders that would produce the same keys for the same
        entities with the same capability — the second is wasted work.
        Returned as (keep, cancel) pairs, deterministic order."""
        seen: dict[tuple, WorkOrder] = {}
        pairs: list[tuple[WorkOrder, WorkOrder]] = []
        candidates = sorted(
            (o for o in self.orders.values()
             if o.status == WorkStatus.PENDING and o.produces),
            key=lambda o: (o.priority, o.objective, o.id),
        )
        for order in candidates:
            key = (order.capability,
                   tuple(sorted(order.produces)),
                   tuple(sorted(e.lower() for e in order.entities)))
            if key in seen:
                pairs.append((seen[key], order))
            else:
                seen[key] = order
        return pairs

    def cascade_failure(self, failed_id: str) -> list[WorkOrder]:
        """Mark every order that transitively lost a required dependency
        SKIPPED, with the causing order named. Skipped work is honest:
        it never ran, and the mission result says why."""
        skipped: list[WorkOrder] = []
        frontier = [failed_id]
        while frontier:
            cause = frontier.pop()
            for order in self.orders.values():
                if order.status != WorkStatus.PENDING:
                    continue
                if cause in order.depends_on:
                    order.status = WorkStatus.SKIPPED
                    order.status_reason = f"dependency {cause} did not complete"
                    skipped.append(order)
                    frontier.append(order.id)
        return skipped

    def resolve_stall(self) -> list[WorkOrder]:
        """A stalled graph has pending orders waiting on terminal-but-not-
        completed dependencies; cascade them so the mission can finish
        honestly instead of spinning."""
        released: list[WorkOrder] = []
        for order in list(self.orders.values()):
            if order.status in (WorkStatus.FAILED, WorkStatus.CANCELLED,
                                WorkStatus.SKIPPED):
                released.extend(self.cascade_failure(order.id))
        return released

    # ------------------------------------------------------------- reading

    def get(self, order_id: str) -> Optional[WorkOrder]:
        return self.orders.get(order_id)

    def progress(self) -> float:
        if not self.orders:
            return 1.0
        completed = sum(1 for o in self.orders.values()
                        if o.status == WorkStatus.COMPLETED)
        return completed / len(self.orders)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for order in self.orders.values():
            counts[order.status.value] = counts.get(order.status.value, 0) + 1
        return counts
