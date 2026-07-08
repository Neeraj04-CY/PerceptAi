"""Live event relay — fan runner-ingested events out to dashboard viewers.

When a runner POSTs a batch of wire-v1 events, the ingest handler persists
them AND publishes them here; any dashboard SSE stream subscribed to that
session receives them in real time. This is the "full live relay" that makes
the Sprint 3 cockpit work live over a REMOTE runner.

In-process, single-host by design (like control_registry): the runner's
ingest and the viewer's SSE stream reach the same API process. A viewer
always backfills from the persisted stream first, so nothing is lost if it
connects mid-run or the relay drops an event — the DB is the source of truth,
the relay is only the low-latency path. A multi-worker deployment would swap
this module for Redis pub/sub without changing the endpoints.
"""
from __future__ import annotations

import queue
import threading
from collections import defaultdict
from typing import Any


class Relay:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[queue.Queue]] = defaultdict(set)

    def subscribe(self, session_id: str) -> "queue.Queue[dict]":
        q: "queue.Queue[dict]" = queue.Queue(maxsize=4000)
        with self._lock:
            self._subscribers[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: "queue.Queue[dict]") -> None:
        with self._lock:
            subs = self._subscribers.get(session_id)
            if subs:
                subs.discard(q)
                if not subs:
                    self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, events: list[dict[str, Any]]) -> None:
        """Non-blocking fan-out; a slow/full viewer queue drops rather than
        stalling ingest — the viewer backfills the gap from the DB anyway."""
        with self._lock:
            subs = list(self._subscribers.get(session_id, ()))
        for q in subs:
            for e in events:
                try:
                    q.put_nowait(e)
                except queue.Full:
                    pass


_relay = Relay()


def relay() -> Relay:
    return _relay
