from fastapi import APIRouter, Depends, Query

from auth import get_current_user
from database import get_service_db
from analytics import build_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])

_RANGES = {"7d": 7, "30d": 30, "90d": 90}
_KINDS = {"all", "task", "mission"}


@router.get("/summary")
async def analytics_summary(
    range: str = Query("30d"),
    kind: str = Query("all"),
    current_user: dict = Depends(get_current_user),
):
    """Unified analytics over this user's tasks and missions. The response
    shape is the stable contract (see api/analytics.py); the aggregation
    happens API-side over a bounded window."""
    days = _RANGES.get(range, 30)
    resolved_kind = kind if kind in _KINDS else "all"
    db = get_service_db()
    return build_summary(db, current_user["sub"], days, resolved_kind)
