"""Platform introspection: templates, capabilities, health and replay.

The capabilities endpoint reads the SAME SpecialistRegistry the workforce
runs on (including `perceptai.specialists` entry-point plugins) — the
plugin surface is observable, never a hardcoded list.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from config import config
from database import get_service_db
from templates import TEMPLATES

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/templates")
async def list_templates():
    return TEMPLATES


@router.get("/capabilities")
async def capabilities(current_user: dict = Depends(get_current_user)):
    """Registered specialists and their capabilities, from the live
    registry (builtins + entry-point plugins). Degrades honestly on
    hosts without engine dependencies."""
    try:
        from perceptai.workforce import SpecialistRegistry, RunnerPool
        from perceptai.workforce.specialist import builtin_specialists
    except Exception as e:
        return {"available": False, "reason": f"engine unavailable: {e}",
                "specialists": [], "capabilities": []}
    registry = SpecialistRegistry()
    # Sessions are created lazily on lease; listing profiles never touches
    # the desktop.
    for specialist in builtin_specialists(RunnerPool(lambda: None)):
        registry.register(specialist)
    plugins = registry.discover()
    return {
        "available": True,
        "specialists": [
            {**r.profile.to_dict(), "healthy": r.healthy()}
            for r in registry.records()
        ],
        "capabilities": registry.capabilities(),
        "plugin_count": plugins,
    }


@router.get("/health")
async def platform_health():
    """Operational truth for the status strip: what this host can actually
    do right now."""
    db_ok = True
    try:
        get_service_db().table("plans").select("id").limit(1).execute()
    except Exception:
        db_ok = False
    from executor import engine_available
    engine_ok, engine_reason = engine_available()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": db_ok,
        "engine": engine_ok,
        "engine_reason": engine_reason,
        "execution_host": engine_ok,  # execution happens on this machine
        "scheduler": config.ENABLE_SCHEDULER,
        "environment": config.ENVIRONMENT,
    }


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, after_seq: int = 0,
                         current_user: dict = Depends(get_current_user)):
    """Replay for single-task sessions: reasoning trace, decisions,
    world snapshots — the persisted canonical stream."""
    db = get_service_db()
    owner = db.table("sessions").select("id").eq("id", session_id).eq(
        "user_id", current_user["sub"]).execute().data
    if not owner:
        raise HTTPException(404, "Session not found")
    rows = db.table("events").select("seq, type, task_id, ts, payload").eq(
        "owner_kind", "session").eq("owner_id", session_id).gt(
        "seq", after_seq).order("seq").limit(2000).execute().data or []
    return rows
