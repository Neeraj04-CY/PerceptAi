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
