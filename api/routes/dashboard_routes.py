from fastapi import APIRouter, Depends
from models import DashboardResponse, UsageResponse, SessionDetail
from auth import get_current_user
from database import get_service_db
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardResponse)
async def get_stats(current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id = current_user["sub"]
    month = datetime.now().strftime("%Y-%m")
    
    # Get all sessions
    sessions = db.table("sessions").select("*").eq(
        "user_id", user_id
    ).order("created_at", desc=True).limit(50).execute()
    
    all_sessions = sessions.data or []
    
    completed = [s for s in all_sessions if s["status"] == "completed"]
    failed = [s for s in all_sessions if s["status"] == "failed"]
    
    # Get usage
    usage = db.table("usage").select("executions").eq(
        "user_id", user_id
    ).eq("month", month).execute()
    
    executions_used = usage.data[0]["executions"] if usage.data else 0
    
    # Get plan
    plan = db.table("user_plans").select("plan_id").eq(
        "user_id", user_id
    ).execute()
    plan_id = plan.data[0]["plan_id"] if plan.data else "free"
    
    limits = {"free": 100, "builder": 10000, "scale": 999999}
    
    recent = [{
        "id": s["id"],
        "instruction": s["instruction"],
        "status": s["status"],
        "execution_time": s.get("execution_time"),
        "steps_count": len(s.get("steps") or []),
        "created_at": s["created_at"]
    } for s in all_sessions[:10]]
    
    return DashboardResponse(
        total_sessions=len(all_sessions),
        successful_sessions=len(completed),
        failed_sessions=len(failed),
        total_executions_this_month=executions_used,
        executions_limit=limits.get(plan_id, 100),
        recent_sessions=recent,
        plan=plan_id
    )

@router.get("/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    result = db.table("sessions").select("*").eq(
        "user_id", current_user["sub"]
    ).order("created_at", desc=True).limit(20).execute()
    return result.data or []

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_service_db()
    result = db.table("sessions").select("*").eq(
        "id", session_id
    ).eq("user_id", current_user["sub"]).execute()
    
    if not result.data:
        from fastapi import HTTPException
        raise HTTPException(404, "Session not found")
    
    return result.data[0]

@router.get("/usage", response_model=UsageResponse)
async def get_usage(current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id = current_user["sub"]
    month = datetime.now().strftime("%Y-%m")
    
    usage = db.table("usage").select("executions").eq(
        "user_id", user_id
    ).eq("month", month).execute()
    
    plan = db.table("user_plans").select("plan_id").eq(
        "user_id", user_id
    ).execute()
    
    plan_id = plan.data[0]["plan_id"] if plan.data else "free"
    limits = {"free": 100, "builder": 10000, "scale": 999999}
    limit = limits.get(plan_id, 100)
    used = usage.data[0]["executions"] if usage.data else 0
    
    return UsageResponse(
        month=month,
        executions_used=used,
        executions_limit=limit,
        plan=plan_id,
        percentage_used=round((used / limit) * 100, 1)
    )