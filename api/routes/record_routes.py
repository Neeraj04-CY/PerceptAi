"""The Organizational Record routes: search and timeline.

Everything the company did, grounded and linked — the API surface that
makes PerceptAI infrastructure, not just a UI."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

import org_record
from auth import get_current_user
from database import get_service_db
from orgs import ensure_personal_org, require_permission

router = APIRouter(tags=["record"])


def _org(db, current_user, org_id: Optional[str]) -> str:
    if org_id is None:
        org_id = ensure_personal_org(db, current_user["sub"],
                                     current_user.get("email", ""))["id"]
    require_permission(db, org_id, current_user["sub"], "view")
    return org_id


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=200),
                 limit: int = 20, org_id: Optional[str] = None,
                 current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    return org_record.search(db, _org(db, current_user, org_id), q,
                             limit=min(max(limit, 1), 50))


@router.get("/timeline")
async def timeline(limit: int = 50, org_id: Optional[str] = None,
                   current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    return org_record.timeline(db, _org(db, current_user, org_id), limit=limit)
