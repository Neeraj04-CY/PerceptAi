"""Runner endpoints — the control plane's distributed-execution surface.

Two audiences, two credentials:
  * Operators (JWT): register runners, list the fleet, dispatch remote work.
  * Runners (X-Runner-Token): heartbeat, claim signed work.

The plane never pushes to a runner; runners PULL (long-poll claim) so they need
no inbound connectivity — the pattern that scales to thousands behind NAT. All
logic lives in runners.py; these handlers stay thin.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

import execution_control as ctrl
import runners as runner_svc
from auth import get_current_user
from config import config
from database import get_service_db
from events_store import ingest_events
from orgs import ensure_personal_org

router = APIRouter(prefix="/runners", tags=["runners"])


class RegisterRunnerRequest(BaseModel):
    name: str = "runner"
    workspace_id: Optional[str] = None
    capabilities: dict = {}


class HeartbeatRequest(BaseModel):
    current_session_id: Optional[str] = None


class DispatchRequest(BaseModel):
    instruction: str
    workspace_id: Optional[str] = None
    workflow_id: Optional[str] = None


class EventsBatch(BaseModel):
    events: list[dict] = []


class ResultReport(BaseModel):
    status: str
    result: Optional[dict] = None
    steps: list[dict] = []
    execution_time: float = 0.0
    error: Optional[str] = None
    events: list[dict] = []  # optional final flush; ingested idempotently


class ApprovalRequestBody(BaseModel):
    request: dict  # the ApprovalRequest the runtime raised


def get_current_runner(x_runner_token: str = Header(..., alias="X-Runner-Token")) -> dict:
    """Resolve the runner-scoped token to its row (401 on failure)."""
    return runner_svc.authenticate_runner(get_service_db(), x_runner_token)


# ---------------------------------------------------------- operator (JWT)

@router.post("")
async def register_runner(body: RegisterRunnerRequest,
                          current_user: dict = Depends(get_current_user)):
    """Register a runner in the caller's org. Returns the token AND signing
    key exactly once — they are never recoverable afterwards."""
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"], current_user.get("email", ""))
    result = runner_svc.register_runner(
        db, user_id=current_user["sub"], org_id=org["id"], name=body.name,
        workspace_id=body.workspace_id, capabilities=body.capabilities,
    )
    from orgs import record_audit
    record_audit(db, org["id"], current_user["sub"], current_user.get("email", ""),
                 "runner.registered", target=f"runner:{result['runner']['id']}",
                 detail={"name": body.name})
    return result


@router.get("")
async def list_runners(current_user: dict = Depends(get_current_user)):
    """The org's runner fleet, with derived live status."""
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"], current_user.get("email", ""))
    return runner_svc.list_runners(db, org["id"])


@router.post("/dispatch")
async def dispatch_run(body: DispatchRequest,
                       current_user: dict = Depends(get_current_user)):
    """Enqueue a remote task for the fleet to claim. Dispatch primitive — the
    full route-to-runner UX lands in the dashboard; the runner never creates
    its own work."""
    if not body.instruction.strip():
        raise HTTPException(422, "instruction is required")
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"], current_user.get("email", ""))
    session = runner_svc.enqueue_session(
        db, user_id=current_user["sub"], org_id=org["id"],
        instruction=body.instruction, workspace_id=body.workspace_id,
        workflow_id=body.workflow_id,
    )
    return {"session_id": session["id"], "status": session["status"]}


# ------------------------------------------------------- runner (X-Runner-Token)

@router.post("/heartbeat")
async def heartbeat(body: HeartbeatRequest, runner: dict = Depends(get_current_runner)):
    """Liveness ping; renews the lease on the runner's current session."""
    runner_svc.record_heartbeat(get_service_db(), runner["id"],
                                current_session_id=body.current_session_id)
    return {"ok": True, "lease_seconds": config.RUNNER_LEASE_SECONDS}


@router.post("/claim")
async def claim_work(runner: dict = Depends(get_current_runner)):
    """Long-poll claim: returns a signed work order, or an empty 204 when the
    queue is empty. Atomic — two runners never claim the same session."""
    db = get_service_db()
    # Lazy recovery: reclaim any sessions whose runner went away, so stale work
    # re-enters the queue (or dead-letters) before we hand out new work.
    runner_svc.reclaim_stale(db)
    session = runner_svc.claim_next(db, runner)
    if session is None:
        return Response(status_code=204)
    runner_svc.record_heartbeat(db, runner["id"], current_session_id=session["id"])
    return runner_svc.issue_work_order(db, runner, session)


def _owned_session(db, session_id: str, runner: dict) -> dict:
    """Fetch a session and confirm THIS runner holds its claim (else 403/404).
    A runner only ever touches work it was assigned."""
    rows = db.table("sessions").select("*").eq("id", session_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Session not found")
    session = rows[0]
    if str(session.get("runner_id")) != str(runner["id"]):
        raise HTTPException(403, "Session is not claimed by this runner")
    return session


@router.post("/executions/{session_id}/events")
async def ingest_execution_events(session_id: str, body: EventsBatch,
                                  runner: dict = Depends(get_current_runner)):
    """Persist a batch of wire-v1 events from the runner (idempotent on seq).
    Returns the resume point so a reconnecting runner never re-sends. First
    batch flips the claim to 'running'."""
    db = get_service_db()
    session = _owned_session(db, session_id, runner)
    if session.get("status") == "claimed":
        db.table("sessions").update({"status": "running"}).eq("id", session_id).execute()
    stored_through = ingest_events(db, "session", session_id, body.events)
    # Fan out live to any connected dashboard viewer (the DB stays the source
    # of truth; the relay is only the low-latency path).
    from relay import relay
    relay().publish(session_id, body.events)
    return {"ok": True, "stored_through": stored_through}


@router.post("/executions/{session_id}/result")
async def report_execution_result(session_id: str, body: ResultReport,
                                  runner: dict = Depends(get_current_runner)):
    """Terminal report: persist the TaskResult, close out the session, free
    the runner, and count usage. Any trailing events are flushed idempotently."""
    db = get_service_db()
    session = _owned_session(db, session_id, runner)
    if body.events:
        ingest_events(db, "session", session_id, body.events)
    db.table("sessions").update({
        "status": body.status,
        "steps": body.steps,
        "result": body.result,
        "error": body.error,
        "execution_time": body.execution_time,
        "runner_id": None,
        "claim_expires_at": None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
    db.table("runners").update({
        "current_session_id": None, "status": "online",
    }).eq("id", runner["id"]).execute()
    try:
        from routes.execute_routes import increment_usage
        if session.get("user_id"):
            increment_usage(session["user_id"], session_id)
    except Exception:
        pass
    return {"ok": True}


@router.get("/executions/{session_id}/control")
async def read_execution_control(session_id: str,
                                 runner: dict = Depends(get_current_runner)):
    """The runner reads durable control (state + any approval decision) that
    the operator set on the plane. This is the network side of the Sprint 3
    ControlChannel — the engine is unaware it is crossing a wire."""
    db = get_service_db()
    _owned_session(db, session_id, runner)
    control = ctrl.get_control(db, session_id)
    return {"state": control.get("state", "running"),
            "approval_decision": control.get("approval_decision")}


@router.post("/executions/{session_id}/approval-request")
async def post_execution_approval_request(session_id: str, body: ApprovalRequestBody,
                                          runner: dict = Depends(get_current_runner)):
    """The runtime raised a risk-gated approval; record it durably so the
    operator's decision can be matched back to it."""
    db = get_service_db()
    _owned_session(db, session_id, runner)
    ctrl.set_approval_request(db, session_id, body.request)
    return {"ok": True}
