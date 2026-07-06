"""Execution control endpoints — the trust layer's live interruptibility.

A running task exposes a control channel (pause / resume / stop) and, when
its workspace risk policy asks, a live approval gate. The client learns the
execution id from the stream's `session_id` event, then drives these
endpoints. Every intervention is a first-class, audited action; the engine
reads the result at its per-cycle checkpoint.

Auth mirrors the streaming surface (X-API-Key), and every call verifies the
execution belongs to the key's user before touching the channel.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from control_registry import registry
from database import get_service_db
from perceptai.contracts import ApprovalDecision

router = APIRouter(prefix="/executions", tags=["control"])

_CONTROL_ACTIONS = {"pause", "resume", "stop"}
_DECISIONS = {"grant": ApprovalDecision.GRANT, "deny": ApprovalDecision.DENY}


class ControlRequest(BaseModel):
    action: str  # pause | resume | stop


class ApprovalRequestBody(BaseModel):
    decision: str  # grant | deny
    reason: str = ""


def _authorize(session_id: str, x_api_key: str) -> dict:
    """Validate the key and confirm it owns this execution. Returns the
    session row. The control channel must live on THIS host/process."""
    from routes.execute_routes import validate_api_key

    key_data = validate_api_key(x_api_key)
    db = get_service_db()
    rows = db.table("sessions").select("*").eq("id", session_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Execution not found")
    session = rows[0]
    if session.get("user_id") != key_data["user_id"]:
        raise HTTPException(403, "Not your execution")
    session["_key_user"] = key_data["user_id"]
    return session


def _audit(session: dict, action: str, detail: dict) -> None:
    if not session.get("org_id"):
        return
    try:
        from orgs import record_audit
        record_audit(
            get_service_db(), session["org_id"], session.get("user_id"), "",
            action, target=f"execution:{session['id']}",
            detail=detail, workspace_id=session.get("workspace_id"),
        )
    except Exception:
        pass


@router.get("/{session_id}/control")
async def get_control(session_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
    """The live control state and any pending approval. 409 once the run has
    ended and its channel is gone — the client should stop polling."""
    _authorize(session_id, x_api_key)
    channel = registry().get(session_id)
    if channel is None:
        raise HTTPException(409, "Execution is not live (already finished)")
    return channel.snapshot()


@router.post("/{session_id}/control")
async def post_control(session_id: str, body: ControlRequest,
                       x_api_key: str = Header(..., alias="X-API-Key")):
    action = (body.action or "").strip().lower()
    if action not in _CONTROL_ACTIONS:
        raise HTTPException(422, f"Unknown control action '{body.action}'")
    session = _authorize(session_id, x_api_key)
    channel = registry().get(session_id)
    if channel is None:
        raise HTTPException(409, "Execution is not live (already finished)")

    if action == "pause":
        channel.pause()
    elif action == "resume":
        channel.resume()
    else:
        channel.stop()

    _audit(session, f"execution.{action}", {"at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, **channel.snapshot()}


@router.post("/{session_id}/approvals/{request_id}")
async def decide_approval(session_id: str, request_id: str, body: ApprovalRequestBody,
                          x_api_key: str = Header(..., alias="X-API-Key")):
    decision = (body.decision or "").strip().lower()
    if decision not in _DECISIONS:
        raise HTTPException(422, f"Decision must be grant or deny, got '{body.decision}'")
    session = _authorize(session_id, x_api_key)
    channel = registry().get(session_id)
    if channel is None:
        raise HTTPException(409, "Execution is not live (already finished)")

    settled = channel.resolve_approval(
        request_id, _DECISIONS[decision],
        decided_by=session.get("user_id") or "", reason=body.reason,
    )
    if not settled:
        raise HTTPException(409, "No matching pending approval (already decided or expired)")

    _audit(session, f"execution.approval.{decision}",
           {"request_id": request_id, "reason": body.reason})
    return {"ok": True, "decision": decision}
