"""Approvals: the human checkpoint as durable records.

Pending rows are created by the mission approver when a capability
requires approval; deciding here authorizes (or refuses) the next
matching dispatch. Every decision is audited.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_service_db
from models import ApprovalDecisionRequest
from orgs import ensure_personal_org, record_audit, require_permission, utc_now

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("")
async def list_approvals(status: str = "pending", limit: int = 50,
                         org_id: Optional[str] = None,
                         current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    if org_id is None:
        org_id = ensure_personal_org(db, current_user["sub"],
                                     current_user.get("email", ""))["id"]
    require_permission(db, org_id, current_user["sub"], "view")
    query = db.table("approvals").select("*").eq("org_id", org_id)
    if status != "all":
        query = query.eq("status", status)
    rows = query.order("created_at", desc=True).limit(
        min(max(limit, 1), 200)).execute().data or []
    return rows


@router.post("/{approval_id}/decide")
async def decide(approval_id: str, body: ApprovalDecisionRequest,
                 current_user: dict = Depends(get_current_user)):
    if body.decision not in ("approved", "denied"):
        raise HTTPException(400, "decision must be 'approved' or 'denied'")
    db = get_service_db()
    rows = db.table("approvals").select("*").eq("id", approval_id).execute().data
    if not rows:
        raise HTTPException(404, "Approval not found")
    approval = rows[0]
    require_permission(db, approval["org_id"], current_user["sub"],
                       "approvals.decide")
    if approval["status"] != "pending":
        raise HTTPException(409, f"Approval already {approval['status']}")
    db.table("approvals").update({
        "status": body.decision,
        "decided_by": current_user["sub"],
        "reason": body.reason,
        "decided_at": utc_now(),
    }).eq("id", approval_id).execute()
    record_audit(db, approval["org_id"], current_user["sub"],
                 current_user.get("email", ""), f"approval.{body.decision}",
                 approval["capability"],
                 {"objective": approval.get("objective", ""),
                  "mission_id": approval.get("mission_id")},
                 workspace_id=approval.get("workspace_id"))

    # Human teaching: an explicit lesson — or a denial with a reason — becomes
    # organizational memory the next run recalls. Best-effort, never blocks
    # the decision.
    taught = (body.lesson or "").strip()
    if not taught and body.decision == "denied" and (body.reason or "").strip():
        taught = f"'{approval['capability']}' was denied: {body.reason.strip()}"
    if taught:
        try:
            import memory_service
            memory_service.teach(
                db, approval["org_id"], current_user["sub"],
                subject=approval["capability"], lesson=taught,
                kind="correction",
                workspace_id=approval.get("workspace_id"),
                evidence_ref={"approval_id": approval_id})
        except Exception:
            pass
    return {"id": approval_id, "status": body.decision}
