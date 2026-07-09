"""The Attention inbox — the operator's view of everything unattended
operations need a human for. Read + ack only: items are created exclusively
by the plane from persisted facts (failed runs, dead-letters, pending
approvals, blocked schedules); nothing is authored here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from attention import ack_attention, list_attention
from auth import get_current_user
from database import get_service_db
from orgs import ensure_personal_org, require_permission

router = APIRouter(prefix="/attention", tags=["attention"])

ATTENTION_HINT = ("attention tables unavailable — apply "
                  "api/migrations/004_operations.sql to this database")


def _resolve_org(db, current_user: dict, org_id: Optional[str],
                 permission: str) -> str:
    if org_id:
        require_permission(db, org_id, current_user["sub"], permission)
        return org_id
    org = ensure_personal_org(db, current_user["sub"],
                              current_user.get("email", ""))
    require_permission(db, org["id"], current_user["sub"], permission)
    return org["id"]


@router.get("")
async def inbox(org_id: Optional[str] = None, status: str = "open",
                current_user: dict = Depends(get_current_user)):
    if status not in ("open", "acked"):
        raise HTTPException(422, "status must be open or acked")
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "view")
    try:
        return list_attention(db, resolved, status=status)
    except Exception as e:
        if "attention" in str(e).lower() and "exist" in str(e).lower():
            raise HTTPException(503, ATTENTION_HINT)
        raise


@router.post("/{item_id}/ack")
async def ack(item_id: str, org_id: Optional[str] = None,
              current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    resolved = _resolve_org(db, current_user, org_id, "execute")
    if not ack_attention(db, resolved, item_id, current_user["sub"]):
        raise HTTPException(404, "No open attention item with that id")
    return {"ok": True}
