"""Canonical event stream for the PerceptAI runtime.

The engine emits exactly one stream of TaskEvents. Every consumer
(CLI, SSE, database persistence, analytics, future replay, future
runner protocol) subscribes to this stream. No consumer builds its
own events from scratch.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .contracts import _plain, utc_now_iso


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    GOAL_ANALYZED = "goal_analyzed"
    WORLD_SNAPSHOT = "world_snapshot"
    EVIDENCE_COLLECTED = "evidence_collected"
    PLAN_CREATED = "plan_created"
    REPLANNED = "replanned"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    HEALING_STARTED = "healing_started"
    HEALING_RESULT = "healing_result"
    VERIFICATION = "verification"
    LOG = "log"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"
    # Reasoning stream (Chapter 4). Every reasoning-cycle transition is
    # observable and replayable; consumers derive views, never rebuild them.
    STRATEGY_SELECTED = "strategy_selected"
    DECISION_MADE = "decision_made"
    BELIEF_UPDATED = "belief_updated"
    UNCERTAINTY_CHANGED = "uncertainty_changed"
    PROGRESS_UPDATED = "progress_updated"
    HYPOTHESIS_CREATED = "hypothesis_created"
    HYPOTHESIS_RESOLVED = "hypothesis_resolved"  # confirmed or rejected
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    # Trust layer (Sprint 3). Control and governance ride the same canonical
    # bus: pause/resume/stop are read at the per-cycle checkpoint, risk is
    # observed per step, approval is a live grant-ahead gate. Consumers (the
    # cockpit, the trust-timeline replay, the audit log) derive views; they
    # never rebuild these.
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_RESUMED = "execution_resumed"
    EXECUTION_STOPPED = "execution_stopped"
    RISK_FLAGGED = "risk_flagged"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    # Audit that a secret was injected — the NAME only, never the value.
    SECRET_USED = "secret_used"
    # Mission stream (Chapter 5). The workforce layer emits on the same
    # canonical bus; task_id carries the mission id, payloads carry work
    # order ids. Consumers derive mission views, never rebuild them.
    MISSION_STARTED = "mission_started"
    MISSION_PLANNED = "mission_planned"
    MISSION_DECISION = "mission_decision"
    WORK_DISPATCHED = "work_dispatched"
    WORK_COMPLETED = "work_completed"
    EVIDENCE_MERGED = "evidence_merged"
    MISSION_COMPLETED = "mission_completed"


@dataclass
class TaskEvent:
    type: EventType
    session_id: str
    task_id: str
    seq: int
    timestamp: str = field(default_factory=utc_now_iso)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(self)


Subscriber = Callable[[TaskEvent], None]


class EventBus:
    """Synchronous, ordered event dispatch. A failing subscriber never
    breaks the run or other subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._seq = 0
        self._lock = threading.Lock()

    def subscribe(self, fn: Subscriber) -> Subscriber:
        self._subscribers.append(fn)
        return fn

    def unsubscribe(self, fn: Subscriber) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def emit(self, type: EventType, session_id: str, task_id: str, **payload: Any) -> TaskEvent:
        with self._lock:
            self._seq += 1
            seq = self._seq
        event = TaskEvent(type=type, session_id=session_id, task_id=task_id, seq=seq, payload=payload)
        for fn in list(self._subscribers):
            try:
                fn(event)
            except Exception:
                # Observability must never take down execution.
                pass
        return event
