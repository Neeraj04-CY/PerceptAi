"""Business Memory routes: what the organization knows, and teaching it.

Reading shows the compounding record; teaching writes an authoritative
lesson. Insights are computed live from measured history — never stored
guesses. 503s with a named hint when 006 hasn't been applied."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import memory_service
from auth import get_current_user
from database import get_service_db
from orgs import ensure_personal_org, record_audit, require_permission

router = APIRouter(prefix="/memory", tags=["memory"])


def _org(db, current_user, org_id: Optional[str]) -> str:
    if org_id is None:
        org_id = ensure_personal_org(db, current_user["sub"],
                                     current_user.get("email", ""))["id"]
    return org_id


def _memory_ready(e: Exception) -> HTTPException:
    return HTTPException(503, "Business Memory unavailable — apply "
                              f"api/migrations/006_business_memory.sql ({e})")


@router.get("")
async def list_memory(kind: Optional[str] = None, org_id: Optional[str] = None,
                      current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    org = _org(db, current_user, org_id)
    require_permission(db, org, current_user["sub"], "view")
    try:
        lessons = memory_service.list_memory(db, org, kind=kind)
        insights = memory_service.approval_insights(db, org)
    except Exception as e:
        raise _memory_ready(e)
    return {"lessons": lessons, "insights": insights}


class TeachRequest(BaseModel):
    lesson: str = Field(min_length=3, max_length=600)
    subject: str = Field(default="general", max_length=120)
    kind: str = Field(default="correction")   # correction | policy | preference | quirk
    scope: str = Field(default="org")         # org | app:<name> | workflow:<id>
    workspace_id: Optional[str] = None
    org_id: Optional[str] = None


@router.post("/teach")
async def teach(body: TeachRequest,
                current_user: dict = Depends(get_current_user)):
    if body.kind not in ("correction", "policy", "preference", "quirk"):
        raise HTTPException(400, "kind must be correction|policy|preference|quirk")
    db = get_service_db()
    org = _org(db, current_user, body.org_id)
    require_permission(db, org, current_user["sub"], "workflows.edit")
    try:
        row = memory_service.teach(
            db, org, current_user["sub"], subject=body.subject,
            lesson=body.lesson, kind=body.kind, scope=body.scope,
            workspace_id=body.workspace_id)
    except Exception as e:
        raise _memory_ready(e)
    record_audit(db, org, current_user["sub"], current_user.get("email", ""),
                 "memory.taught", body.subject, {"kind": body.kind, "scope": body.scope})
    return row


@router.delete("/{memory_id}")
async def forget(memory_id: str, org_id: Optional[str] = None,
                 current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    org = _org(db, current_user, org_id)
    require_permission(db, org, current_user["sub"], "workflows.edit")
    try:
        memory_service.archive(db, org, memory_id)
    except Exception as e:
        raise _memory_ready(e)
    record_audit(db, org, current_user["sub"], current_user.get("email", ""),
                 "memory.archived", memory_id, {})
    return {"archived": memory_id}
