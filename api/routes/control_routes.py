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

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user
from control_registry import registry
from database import get_service_db
from perceptai.contracts import ApprovalDecision
from perceptai.streaming import platform_to_legacy
from relay import relay
from sse import SSE_HEADERS, sse

router = APIRouter(prefix="/executions", tags=["control"])

_TERMINAL = {"completed", "failed", "unverified", "cancelled"}
_STREAM_MAX_S = 1800  # safety bound on a single viewer stream

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


# A remote execution is controllable while its work is live in the queue or on
# a runner; the same control API then routes to the durable store instead of a
# local in-process channel.
_LIVE_REMOTE = {"queued", "claimed", "running"}


def _remote_live(session: dict) -> bool:
    return session.get("status") in _LIVE_REMOTE


@router.get("/{session_id}/control")
async def get_control(session_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
    """The live control state and any pending approval. Local runs read the
    in-process channel; remote runs read the durable store. 409 only once the
    run has genuinely ended."""
    session = _authorize(session_id, x_api_key)
    channel = registry().get(session_id)
    if channel is not None:
        return channel.snapshot()
    if _remote_live(session):
        import execution_control as ctrl
        return ctrl.snapshot(get_service_db(), session_id)
    raise HTTPException(409, "Execution is not live (already finished)")


@router.post("/{session_id}/control")
async def post_control(session_id: str, body: ControlRequest,
                       x_api_key: str = Header(..., alias="X-API-Key")):
    action = (body.action or "").strip().lower()
    if action not in _CONTROL_ACTIONS:
        raise HTTPException(422, f"Unknown control action '{body.action}'")
    session = _authorize(session_id, x_api_key)
    channel = registry().get(session_id)

    if channel is not None:                       # local execution (Sprint 3)
        {"pause": channel.pause, "resume": channel.resume, "stop": channel.stop}[action]()
        result = channel.snapshot()
    elif _remote_live(session):                   # remote execution — durable
        import execution_control as ctrl
        ctrl.set_state(get_service_db(), session_id, ctrl.ACTION_STATE[action])
        result = ctrl.snapshot(get_service_db(), session_id)
    else:
        raise HTTPException(409, "Execution is not live (already finished)")

    _audit(session, f"execution.{action}", {"at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, **result}


@router.post("/{session_id}/approvals/{request_id}")
async def decide_approval(session_id: str, request_id: str, body: ApprovalRequestBody,
                          x_api_key: str = Header(..., alias="X-API-Key")):
    decision = (body.decision or "").strip().lower()
    if decision not in _DECISIONS:
        raise HTTPException(422, f"Decision must be grant or deny, got '{body.decision}'")
    session = _authorize(session_id, x_api_key)
    channel = registry().get(session_id)
    decided_by = session.get("user_id") or ""

    if channel is not None:                       # local execution (Sprint 3)
        settled = channel.resolve_approval(
            request_id, _DECISIONS[decision], decided_by=decided_by, reason=body.reason)
    elif _remote_live(session):                   # remote execution — durable
        import execution_control as ctrl
        settled = ctrl.set_approval_decision(
            get_service_db(), session_id, request_id, decision,
            decided_by=decided_by, reason=body.reason)
    else:
        raise HTTPException(409, "Execution is not live (already finished)")

    if not settled:
        raise HTTPException(409, "No matching pending approval (already decided or expired)")

    _audit(session, f"execution.approval.{decision}",
           {"request_id": request_id, "reason": body.reason})
    # The wait is over — close the matching Attention item so the inbox only
    # ever shows things that still need a human.
    try:
        if session.get("org_id"):
            from attention import ack_attention
            db = get_service_db()
            rows = db.table("attention_items").select("id").eq(
                "org_id", session["org_id"]).eq("kind", "approval_pending").eq(
                "ref", str(session_id)).eq("status", "open").limit(1).execute().data or []
            if rows:
                ack_attention(db, session["org_id"], rows[0]["id"], decided_by)
    except Exception:
        pass
    return {"ok": True, "decision": decision}


# ------------------------------------------------------------- live relay (JWT)

@router.get("/{session_id}/stream")
async def stream_execution(session_id: str,
                           current_user: dict = Depends(get_current_user)):
    """Live view of a REMOTE runner's execution. Backfills the persisted
    stream first (so a mid-run connect misses nothing), then relays new events
    as the runner ingests them — translated wire-v1 -> v0 so the same cockpit
    renders local and remote runs identically."""
    db = get_service_db()
    owner = db.table("sessions").select("id, user_id, status").eq(
        "id", session_id).limit(1).execute().data or []
    if not owner or owner[0].get("user_id") != current_user["sub"]:
        raise HTTPException(404, "Execution not found")

    q = relay().subscribe(session_id)

    def _stream():
        sent: set[int] = set()
        try:
            yield sse({"type": "session_id", "session_id": session_id})

            # Backfill: everything already persisted, in order.
            rows = db.table("events").select("seq, type, task_id, ts, payload").eq(
                "owner_kind", "session").eq("owner_id", session_id).order(
                "seq").limit(2000).execute().data or []
            done = False
            for r in rows:
                seq = int(r.get("seq", 0) or 0)
                sent.add(seq)
                v0 = platform_to_legacy(r["type"], r.get("payload") or {},
                                        r.get("task_id", ""), r.get("ts") or "", seq)
                if v0:
                    yield sse(v0)
                if r["type"] == "task_completed":
                    done = True

            # Already finished before we connected — end cleanly.
            if done or owner[0].get("status") in _TERMINAL:
                return

            # Live: relay new events until completion / terminal / timeout.
            deadline = time.time() + _STREAM_MAX_S
            checks = 0
            while not done and time.time() < deadline:
                drained = False
                while True:
                    try:
                        e = q.get(timeout=0.25)
                    except Exception:
                        break
                    drained = True
                    seq = int(e.get("seq", 0) or 0)
                    if seq in sent:
                        continue
                    sent.add(seq)
                    v0 = platform_to_legacy(e.get("type", ""), e.get("data") or {},
                                            e.get("task_id", ""), e.get("timestamp") or "", seq)
                    if v0:
                        yield sse(v0)
                    if e.get("type") == "task_completed":
                        done = True
                        break
                if not drained:
                    yield ": keepalive\n\n"
                    checks += 1
                    if checks % 8 == 0:  # ~every 2s, confirm the run is still live
                        st = db.table("sessions").select("status").eq(
                            "id", session_id).limit(1).execute().data or []
                        if st and st[0].get("status") in _TERMINAL:
                            break
        finally:
            relay().unsubscribe(session_id, q)

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers=SSE_HEADERS)
