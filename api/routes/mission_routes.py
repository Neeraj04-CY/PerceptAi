"""Mission endpoints: the workforce layer as a product surface.

POST /missions/stream runs one mission (X-API-Key, SSE wire v1 — canonical
event types with nested data). The mission row, its MissionResult and the
full canonical event stream are persisted; GET endpoints serve history,
detail and replay to the dashboard (JWT).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import get_service_db
from events_store import EventBuffer
from models import MissionRequest
from orgs import default_workspace, ensure_personal_org, get_workspace, utc_now
from plans import get_plan
from routes.execute_routes import check_usage_limit, increment_usage, validate_api_key
from sse import KEEPALIVE, SSE_HEADERS, athread_iter, sse

router = APIRouter(prefix="/missions", tags=["missions"])


def _db_approver(db, org_id: str, workspace_id: str, mission_id: str,
                 user_id: str):
    """Grant-ahead approvals: an APPROVED record for this workspace and
    capability is consumed and the order runs; otherwise a PENDING record
    is created and the order is denied honestly. Approving in the
    dashboard authorizes the next run — never a silent bypass."""

    def approve(order) -> bool:
        grants = db.table("approvals").select("id").eq(
            "workspace_id", workspace_id).eq(
            "capability", order.capability).eq(
            "status", "approved").limit(1).execute().data
        if grants:
            db.table("approvals").update({
                "status": "consumed",
                "consumed_at": utc_now(),
                "mission_id": mission_id,
            }).eq("id", grants[0]["id"]).execute()
            return True
        db.table("approvals").insert({
            "org_id": org_id,
            "workspace_id": workspace_id,
            "mission_id": mission_id,
            "capability": order.capability,
            "objective": order.objective[:500],
            "status": "pending",
            "requested_by": user_id,
        }).execute()
        return False

    return approve


@router.post("/stream")
async def run_mission_stream(
    body: MissionRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    from executor import execute_mission_stream

    db = get_service_db()
    key_data = validate_api_key(x_api_key)
    user_id = key_data["user_id"]
    plan_id = key_data.get("plan_id", "free")
    if not check_usage_limit(user_id, plan_id):
        raise HTTPException(429, "Monthly execution limit reached")

    org = ensure_personal_org(db, user_id)
    workspace = (get_workspace(db, body.workspace_id, org["id"])
                 if body.workspace_id else default_workspace(db, org["id"]))
    ws_policy = (workspace or {}).get("policy") or {}
    plan = get_plan(org.get("plan_id") or plan_id, db)

    limits = dict(plan["limits"])
    if ws_policy.get("allowed_capabilities") is not None:
        limits["allowed_capabilities"] = ws_policy["allowed_capabilities"]
    limits["approval_capabilities"] = ws_policy.get("approval_capabilities", [])
    if ws_policy.get("max_cost_per_mission"):
        limits["max_total_cost"] = min(float(limits.get("max_total_cost", 0) or 0),
                                       float(ws_policy["max_cost_per_mission"]))

    mission_id = str(uuid.uuid4())
    db.table("missions").insert({
        "id": mission_id,
        "org_id": org["id"],
        "workspace_id": workspace["id"] if workspace else None,
        "user_id": user_id,
        "api_key_id": key_data["id"],
        "workflow_id": body.workflow_id,
        "instruction": body.instruction,
        "status": "running",
    }).execute()

    stream = execute_mission_stream(
        body.instruction,
        workspace={
            "organization": org.get("slug") or org.get("name", "personal"),
            "project": (workspace or {}).get("slug", "default"),
            "user": user_id,
            "plan": plan["id"],
        },
        limits=limits,
        approver=_db_approver(db, org["id"],
                              workspace["id"] if workspace else None,
                              mission_id, user_id),
    )

    async def generate():
        yield sse({"type": "mission_id", "mission_id": mission_id})
        final = {"status": "failed", "error": None, "result": None,
                 "metrics": None, "execution_time": 0.0, "events": []}
        async for item in athread_iter(stream):
            if item is None:
                yield KEEPALIVE
                continue
            if item.get("type") == "_result":
                final.update({k: item.get(k, final[k]) for k in final})
                continue
            if item.get("type") == "error":
                final["error"] = item.get("message")
            yield sse(item)

        db.table("missions").update({
            "status": final["status"],
            "result": final["result"],
            "metrics": final["metrics"],
            "error": final["error"],
            "duration_s": final["execution_time"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", mission_id).execute()

        buffer = EventBuffer()
        for event in final["events"]:
            buffer.collect(event)
        buffer.flush(db, "mission", mission_id)
        increment_usage(user_id, mission_id)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers=SSE_HEADERS)


# ---------------------------------------------------------------- history

@router.get("")
async def list_missions(limit: int = 25,
                        current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"],
                              current_user.get("email", ""))
    rows = db.table("missions").select(
        "id, instruction, status, metrics, duration_s, workspace_id, "
        "workflow_id, created_at, completed_at").eq(
        "org_id", org["id"]).order("created_at", desc=True).limit(
        min(max(limit, 1), 100)).execute().data or []
    return rows


@router.get("/{mission_id}")
async def mission_detail(mission_id: str,
                         current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"],
                              current_user.get("email", ""))
    rows = db.table("missions").select("*").eq("id", mission_id).eq(
        "org_id", org["id"]).execute().data
    if not rows:
        raise HTTPException(404, "Mission not found")
    return rows[0]


@router.get("/{mission_id}/events")
async def mission_events(mission_id: str, after_seq: int = 0,
                         current_user: dict = Depends(get_current_user)):
    """Replay: the persisted canonical event stream, in order."""
    db = get_service_db()
    org = ensure_personal_org(db, current_user["sub"],
                              current_user.get("email", ""))
    owner = db.table("missions").select("id").eq("id", mission_id).eq(
        "org_id", org["id"]).execute().data
    if not owner:
        raise HTTPException(404, "Mission not found")
    rows = db.table("events").select("seq, type, task_id, ts, payload").eq(
        "owner_kind", "mission").eq("owner_id", mission_id).gt(
        "seq", after_seq).order("seq").limit(2000).execute().data or []
    return rows
