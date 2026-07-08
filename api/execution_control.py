"""Durable execution control — the restart-surviving control channel.

For a REMOTE execution the operator's intent (pause/resume/stop, approval
decisions) must reach a runner in another process, and must survive an API
restart. It lives here, in one row per session, read by the runner's
RemoteControlChannel over the network. Local (API-host) execution keeps using
the in-process control registry from Sprint 3 and never touches this table.

Pure DB accessors; the transport lives in the routes. Both the operator
control endpoints and the runner-facing endpoints go through this module, so
the durable control record has exactly one writer path per field.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# Maps a control action to the durable state it sets.
ACTION_STATE = {"pause": "paused", "resume": "running", "stop": "stopping"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_control(db, session_id: str) -> dict[str, Any]:
    """Current durable control for a session. Defaults to a clean running
    state when no row exists yet (execution just started, nothing to control)."""
    try:
        rows = db.table("execution_control").select("*").eq(
            "session_id", session_id).limit(1).execute().data or []
    except Exception:
        rows = []
    if not rows:
        return {"session_id": session_id, "state": "running",
                "approval_request": None, "approval_decision": None}
    return rows[0]


def _upsert(db, session_id: str, fields: dict[str, Any]) -> None:
    db.table("execution_control").upsert(
        {"session_id": session_id, "updated_at": _now(), **fields}
    ).execute()


def set_state(db, session_id: str, state: str) -> None:
    _upsert(db, session_id, {"state": state})


def set_approval_request(db, session_id: str, request: Optional[dict]) -> None:
    """The runner records a pending approval so the decision can be matched;
    a fresh request clears any stale decision."""
    _upsert(db, session_id, {"approval_request": request, "approval_decision": None})


def set_approval_decision(db, session_id: str, request_id: str,
                          decision: str, decided_by: str = "", reason: str = "") -> bool:
    """Settle the pending approval if the id matches. Returns False when there
    is nothing pending or the id is stale — the caller answers 409."""
    control = get_control(db, session_id)
    pending = control.get("approval_request") or {}
    if not pending or str(pending.get("request_id")) != str(request_id):
        return False
    _upsert(db, session_id, {"approval_decision": {
        "request_id": request_id, "decision": decision,
        "decided_by": decided_by, "reason": reason,
    }})
    return True


def snapshot(db, session_id: str) -> dict[str, Any]:
    """A control view shaped like the in-process channel's snapshot, so the
    operator get-control endpoint returns one schema for local and remote."""
    control = get_control(db, session_id)
    return {
        "state": control.get("state", "running"),
        "pending_approval": control.get("approval_request"),
    }
