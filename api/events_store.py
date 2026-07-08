"""Persistence for the canonical event stream.

One buffer per execution collects TaskEvent dicts as they stream and
bulk-inserts them when the run finishes. Replay, mission timelines and
reasoning traces all read the resulting rows. Persistence failures are
swallowed — observability must never take down execution — but they are
counted so health checks can report them.
"""
from __future__ import annotations

from typing import Any

MAX_EVENTS = 2000     # bound memory per run; beyond this only count
CHUNK = 200           # rows per insert statement


class EventBuffer:
    def __init__(self, max_events: int = MAX_EVENTS):
        self._max = max_events
        self.events: list[dict[str, Any]] = []
        self.dropped = 0

    def collect(self, event: dict[str, Any]) -> None:
        if len(self.events) >= self._max:
            self.dropped += 1
            return
        self.events.append(event)

    def rows(self, owner_kind: str, owner_id: str) -> list[dict[str, Any]]:
        return [
            {
                "owner_kind": owner_kind,
                "owner_id": owner_id,
                "seq": e.get("seq", i + 1),
                "type": str(e.get("type", "")),
                "task_id": str(e.get("task_id", "")),
                "ts": e.get("timestamp"),
                "payload": e.get("payload") or {},
            }
            for i, e in enumerate(self.events)
        ]

    def flush(self, db, owner_kind: str, owner_id: str) -> bool:
        """Bulk-insert collected events. Returns False on failure instead
        of raising — the session result is already persisted elsewhere."""
        rows = self.rows(owner_kind, owner_id)
        if not rows:
            return True
        try:
            for start in range(0, len(rows), CHUNK):
                db.table("events").insert(rows[start:start + CHUNK]).execute()
            return True
        except Exception:
            return False


def current_max_seq(db, owner_kind: str, owner_id: str) -> int:
    """Highest persisted seq for an execution, or 0. Lets a reconnecting
    runner resume streaming from where the plane left off."""
    try:
        rows = db.table("events").select("seq").eq("owner_kind", owner_kind).eq(
            "owner_id", owner_id).order("seq", desc=True).limit(1).execute().data or []
        return int(rows[0]["seq"]) if rows else 0
    except Exception:
        return 0


def ingest_events(db, owner_kind: str, owner_id: str,
                  events: list[dict[str, Any]]) -> int:
    """Idempotently persist wire-v1 events from a runner. Only rows with a
    seq greater than what is already stored are inserted, so a retried or
    reconnecting runner never creates duplicates — the plane's stored stream
    is the source of truth. Returns the new max seq (the resume point)."""
    stored = current_max_seq(db, owner_kind, owner_id)
    fresh = [e for e in events if int(e.get("seq", 0) or 0) > stored]
    if not fresh:
        return stored
    rows = [
        {
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "seq": int(e.get("seq", 0) or 0),
            "type": str(e.get("type", "")),
            "task_id": str(e.get("task_id", "")),
            "ts": e.get("timestamp") or e.get("ts"),
            "payload": e.get("payload") or e.get("data") or {},
        }
        for e in fresh
    ]
    rows.sort(key=lambda r: r["seq"])
    try:
        for start in range(0, len(rows), CHUNK):
            db.table("events").insert(rows[start:start + CHUNK]).execute()
        return rows[-1]["seq"]
    except Exception:
        return stored
