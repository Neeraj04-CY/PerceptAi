"""Agent Studio: workflows as versioned, parametrized instructions.

A workflow compiles to the ONE runtime — plain English with {{variable}}
slots, run as a task or a mission. Branching and parallelism live in the
engine's WorkGraph; there is deliberately no second workflow interpreter.
Publishing snapshots an immutable version; rendering resolves variables
so the client executes through the same streaming endpoints as any run.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_service_db
from models import (
    WorkflowCreateRequest,
    WorkflowRenderRequest,
    WorkflowUpdateRequest,
)
from orgs import (
    ensure_personal_org,
    get_workspace,
    record_audit,
    require_permission,
    utc_now,
)
from templates import get_template, render_instruction

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _resolve_org(db, current_user: dict, org_id: Optional[str],
                 permission: str) -> str:
    if org_id:
        require_permission(db, org_id, current_user["sub"], permission)
        return org_id
    org = ensure_personal_org(db, current_user["sub"],
                              current_user.get("email", ""))
    require_permission(db, org["id"], current_user["sub"], permission)
    return org["id"]


def _get_workflow(db, workflow_id: str, org_id: str) -> dict:
    rows = db.table("workflows").select("*").eq("id", workflow_id).eq(
        "org_id", org_id).execute().data
    if not rows:
        raise HTTPException(404, "Workflow not found")
    return rows[0]


@router.get("")
async def list_workflows(org_id: Optional[str] = None,
                         current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "view")
    rows = db.table("workflows").select(
        "id, name, description, mode, status, version, schedule, "
        "workspace_id, updated_at, created_at").eq("org_id", resolved).neq(
        "status", "archived").order("updated_at", desc=True).execute().data or []
    return rows


@router.post("")
async def create_workflow(body: WorkflowCreateRequest,
                          org_id: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "workflows.edit")
    user_id = current_user["sub"]

    name = body.name.strip()
    instruction = body.instruction.strip()
    variables = body.variables
    mode = body.mode
    description = body.description
    if body.template_id:
        template = get_template(body.template_id)
        if template is None:
            raise HTTPException(404, f"Unknown template '{body.template_id}'")
        instruction = instruction or template["instruction"]
        variables = variables or template["variables"]
        mode = template["mode"] if body.mode == "task" else mode
        description = description or template["description"]
        name = name or template["name"]
    if not name:
        raise HTTPException(400, "Workflow name is required")
    if mode not in ("task", "mission"):
        raise HTTPException(400, "mode must be 'task' or 'mission'")
    if body.workspace_id:
        get_workspace(db, body.workspace_id, resolved)

    created = db.table("workflows").insert({
        "org_id": resolved,
        "workspace_id": body.workspace_id,
        "name": name,
        "description": description,
        "instruction": instruction,
        "variables": variables,
        "mode": mode,
        "policy": body.policy,
        "status": "draft",
        "created_by": user_id,
    }).execute().data[0]
    record_audit(db, resolved, user_id, current_user.get("email", ""),
                 "workflow.created", name, {"template": body.template_id})
    return created


@router.get("/autonomy")
async def fleet_autonomy(org_id: Optional[str] = None,
                         current_user: dict = Depends(get_current_user)):
    """The org's AUTONOMY POSTURE — the command center's trust pillar. Rolls
    per-workflow assurance across every published task workflow into one
    reading: how much of the autonomous workforce has earned self-operation,
    and which workflows look reliable but aren't trustworthy (confident liars).

    Registered BEFORE /{workflow_id} so 'autonomy' is never taken for an id.
    Two queries (workflows + their sessions), grouped and computed in Python —
    the same assurance math at fleet scale. Never a parallel system."""
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "view")
    try:
        workflows = db.table("workflows").select("id, name, mode, status").eq(
            "org_id", resolved).eq("status", "published").execute().data or []
    except Exception:
        workflows = []
    workflows = [w for w in workflows if w.get("mode") != "mission"]
    wf_ids = [w["id"] for w in workflows]

    sessions_by_wf: dict[str, list] = {wid: [] for wid in wf_ids}
    if wf_ids:
        try:
            rows = db.table("sessions").select(
                "workflow_id, status, error, execution_time, result").in_(
                "workflow_id", wf_ids).order(
                "created_at", desc=True).limit(1000).execute().data or []
            for r in rows:
                sessions_by_wf.setdefault(r.get("workflow_id"), []).append(r)
        except Exception:
            pass

    from assurance import fleet_posture
    packed = [{"id": w["id"], "name": w.get("name", ""),
               "sessions": sessions_by_wf.get(w["id"], [])} for w in workflows]
    return fleet_posture(packed)


@router.get("/{workflow_id}")
async def workflow_detail(workflow_id: str, org_id: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "view")
    workflow = _get_workflow(db, workflow_id, resolved)
    versions = db.table("workflow_versions").select(
        "version, published_by, published_at").eq(
        "workflow_id", workflow_id).order("version", desc=True).execute().data or []
    return {**workflow, "versions": versions}


@router.patch("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowUpdateRequest,
                          org_id: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "workflows.edit")
    _get_workflow(db, workflow_id, resolved)
    if body.mode is not None and body.mode not in ("task", "mission"):
        raise HTTPException(400, "mode must be 'task' or 'mission'")
    if body.status is not None and body.status not in ("draft", "archived"):
        raise HTTPException(400, "status can only move to draft or archived here — "
                                 "use /publish to publish")
    patch = {k: v for k, v in {
        "name": body.name, "description": body.description,
        "instruction": body.instruction, "variables": body.variables,
        "mode": body.mode, "policy": body.policy,
        "schedule": body.schedule, "status": body.status,
    }.items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = utc_now()
    updated = db.table("workflows").update(patch).eq(
        "id", workflow_id).execute().data
    record_audit(db, resolved, current_user["sub"],
                 current_user.get("email", ""), "workflow.updated",
                 workflow_id, {"fields": [k for k in patch if k != "updated_at"]})
    return updated[0] if updated else {"id": workflow_id, **patch}


@router.post("/{workflow_id}/publish")
async def publish_workflow(workflow_id: str, org_id: Optional[str] = None,
                           current_user: dict = Depends(get_current_user)):
    """Snapshot the current definition as an immutable version."""
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "workflows.edit")
    workflow = _get_workflow(db, workflow_id, resolved)
    if not workflow.get("instruction", "").strip():
        raise HTTPException(400, "Cannot publish an empty instruction")
    version = int(workflow.get("version") or 0) + 1
    db.table("workflow_versions").insert({
        "workflow_id": workflow_id,
        "version": version,
        "instruction": workflow["instruction"],
        "variables": workflow.get("variables") or [],
        "mode": workflow.get("mode", "task"),
        "policy": workflow.get("policy") or {},
        "published_by": current_user["sub"],
    }).execute()
    db.table("workflows").update({
        "version": version, "status": "published", "updated_at": utc_now(),
    }).eq("id", workflow_id).execute()
    record_audit(db, resolved, current_user["sub"],
                 current_user.get("email", ""), "workflow.published",
                 workflow["name"], {"version": version})
    return {"id": workflow_id, "version": version, "status": "published"}


@router.get("/{workflow_id}/runs")
async def workflow_runs(workflow_id: str, org_id: Optional[str] = None,
                        limit: int = 50,
                        current_user: dict = Depends(get_current_user)):
    """Run history + health for one workflow — 'is this automation reliable?'
    answered from the sessions the plane already persists. Sessions link back
    via workflow_id (scheduled dispatch, remote dispatch and policy retries
    all set it)."""
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "view")
    _get_workflow(db, workflow_id, resolved)
    limit = max(1, min(200, limit))
    # `result` is selected so assurance can read each run's reported confidence
    # and typed failure_type — the raw material for the verified reliability
    # number and its calibration. A separate lean select keeps the runs list
    # (rendered as a table) free of the heavy result JSON.
    fields = ("id, status, origin, error, execution_time, created_at, "
              "completed_at, retry_of, retry_count, runner_id")
    try:
        rows = db.table("sessions").select(fields).eq(
            "workflow_id", workflow_id).order(
            "created_at", desc=True).limit(limit).execute().data or []
        assurance_rows = db.table("sessions").select(
            "status, error, execution_time, result").eq(
            "workflow_id", workflow_id).order(
            "created_at", desc=True).limit(200).execute().data or []
    except Exception as e:
        if "workflow_id" in str(e).lower():
            raise HTTPException(503, "run history unavailable — apply "
                                     "api/migrations/004_operations.sql to this database")
        raise
    terminal = [r for r in rows if r.get("status") in
                ("completed", "failed", "unverified")]
    completed = sum(1 for r in terminal if r["status"] == "completed")

    from assurance import compute_assurance
    return {
        "runs": rows,
        "health": {
            "total": len(terminal),
            "completed": completed,
            "failed": sum(1 for r in terminal if r["status"] == "failed"),
            "unverified": sum(1 for r in terminal if r["status"] == "unverified"),
            "success_rate": round(completed / len(terminal), 3) if terminal else None,
        },
        # The measured reliability ledger + evidence-backed autonomy verdict.
        "assurance": compute_assurance(assurance_rows),
    }


@router.post("/{workflow_id}/render")
async def render_workflow(workflow_id: str, body: WorkflowRenderRequest,
                          org_id: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    """Resolve variables into a runnable instruction. The client then runs
    it through the SAME streaming endpoints as any other execution —
    workflows never get a second execution path."""
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "execute")
    workflow = _get_workflow(db, workflow_id, resolved)
    try:
        instruction = render_instruction(
            workflow.get("instruction", ""),
            workflow.get("variables") or [],
            {k: str(v) for k, v in (body.values or {}).items()},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not instruction:
        raise HTTPException(400, "Workflow renders to an empty instruction")
    return {
        "instruction": instruction,
        "mode": workflow.get("mode", "task"),
        "workflow_id": workflow_id,
        "workspace_id": workflow.get("workspace_id"),
        "version": workflow.get("version") or 0,
    }
