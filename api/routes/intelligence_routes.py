"""Workforce Intelligence route: the workforce's self-review.

One endpoint, computed live from measured rows — the briefing a manager
reads to see how the workforce is evolving, not just what it finished."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

import intelligence
from auth import get_current_user
from database import get_service_db
from orgs import ensure_personal_org, require_permission

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/briefing")
async def get_briefing(org_id: Optional[str] = None,
                       current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    if org_id is None:
        org_id = ensure_personal_org(db, current_user["sub"],
                                     current_user.get("email", ""))["id"]
    require_permission(db, org_id, current_user["sub"], "view")
    return intelligence.briefing(db, org_id)
