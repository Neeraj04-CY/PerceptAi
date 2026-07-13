"""Workforce Intelligence route: the workforce's self-review.

One endpoint, computed live from measured rows — the briefing a manager
reads to see how the workforce is evolving, not just what it finished."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

import intelligence
import org_graph
from auth import get_current_user
from database import get_service_db
from orgs import ensure_personal_org, require_permission

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _org(db, current_user, org_id: Optional[str]) -> str:
    if org_id is None:
        org_id = ensure_personal_org(db, current_user["sub"],
                                     current_user.get("email", ""))["id"]
    require_permission(db, org_id, current_user["sub"], "view")
    return org_id


@router.get("/briefing")
async def get_briefing(org_id: Optional[str] = None,
                       current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    return intelligence.briefing(db, _org(db, current_user, org_id))


@router.get("/graph")
async def get_graph(org_id: Optional[str] = None,
                    current_user: dict = Depends(get_current_user)):
    """The Organizational Graph: the business as measured relationships."""
    db = get_service_db()
    return org_graph.build_graph(db, _org(db, current_user, org_id))


@router.get("/discoveries")
async def get_discoveries(org_id: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    """Business discoveries from relationships — evidence, confidence,
    affected departments, impact and one recommended action each."""
    db = get_service_db()
    return org_graph.discoveries(db, _org(db, current_user, org_id))
