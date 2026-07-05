from fastapi import APIRouter, HTTPException, Header
from models import ExecuteRequest, ExecuteResponse
from auth import hash_api_key
from database import get_service_db
from executor import execute_task
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/execute", tags=["execute"])

def validate_api_key(api_key: str) -> dict:
    """Validate API key and return user info"""
    db = get_service_db()
    
    key_hash = hash_api_key(api_key)
    
    # Step 1: Get the API key
    key_result = db.table("api_keys").select("*").eq(
        "key_hash", key_hash
    ).eq("is_active", True).execute()
    
    if not key_result.data:
        raise HTTPException(401, "Invalid API key")
    
    key_data = key_result.data[0]
    user_id = key_data["user_id"]
    
    # Step 2: Get the user plan separately
    plan_result = db.table("user_plans").select("plan_id").eq(
        "user_id", user_id
    ).execute()
    
    plan_id = "free"
    if plan_result.data:
        plan_id = plan_result.data[0]["plan_id"]
    
    # Update last used
    from datetime import timezone
    db.table("api_keys").update({
        "last_used_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", key_data["id"]).execute()
    
    # Return combined data
    key_data["plan_id"] = plan_id
    return key_data

def check_usage_limit(user_id: str, plan_id: str) -> bool:
    """Check if user is within their monthly limit"""
    db = get_service_db()
    month = datetime.now().strftime("%Y-%m")
    
    result = db.table("usage").select("executions").eq(
        "user_id", user_id
    ).eq("month", month).execute()

    from plans import monthly_limit
    limit = monthly_limit(plan_id, db)

    if not result.data:
        return True  # No usage yet

    return result.data[0]["executions"] < limit

def increment_usage(user_id: str, session_id: str):
    """Track usage for billing"""
    db = get_service_db()
    month = datetime.now().strftime("%Y-%m")
    
    existing = db.table("usage").select("id, executions").eq(
        "user_id", user_id
    ).eq("month", month).execute()
    
    if existing.data:
        db.table("usage").update({
            "executions": existing.data[0]["executions"] + 1
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("usage").insert({
            "user_id": user_id,
            "session_id": session_id,
            "month": month,
            "executions": 1
        }).execute()

@router.post("", response_model=ExecuteResponse)
async def execute(
    body: ExecuteRequest,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    # Validate key
    key_data = validate_api_key(x_api_key)
    user_id = key_data["user_id"]
    plan_id = key_data.get("plan_id", "free")
    
    # Check limits
    if not check_usage_limit(user_id, plan_id):
        raise HTTPException(429, "Monthly execution limit reached. Upgrade your plan.")
    
    # Create session record
    session_id = str(uuid.uuid4())
    db = get_service_db()

    from orgs import session_scope
    row = {
        "id": session_id,
        "user_id": user_id,
        "api_key_id": key_data["id"],
        "instruction": body.instruction,
        "status": "running"
    }
    scope = session_scope(db, user_id, body.workspace_id, body.workflow_id)
    try:
        db.table("sessions").insert({**row, **scope}).execute()
    except Exception:
        db.table("sessions").insert(row).execute()
    
    # Execute task through the unified engine
    result, engine_error = execute_task(body.instruction)

    if result is None:
        db.table("sessions").update({
            "status": "failed",
            "error": engine_error,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", session_id).execute()
        increment_usage(user_id, session_id)
        return ExecuteResponse(
            session_id=session_id,
            status="failed",
            instruction=body.instruction,
            steps=[],
            error=engine_error,
            created_at=datetime.now(timezone.utc)
        )

    from perceptai.streaming import legacy_steps
    steps = legacy_steps(result)
    error = "; ".join(result.errors) if result.errors else None

    db.table("sessions").update({
        "status": result.status.value,
        "steps": steps,
        "result": result.to_dict(),
        "execution_time": result.duration_s,
        "error": error,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", session_id).execute()

    increment_usage(user_id, session_id)

    return ExecuteResponse(
        session_id=session_id,
        status=result.status.value,
        instruction=body.instruction,
        steps=steps,
        execution_time=result.duration_s,
        error=error,
        summary=result.summary,
        confidence=result.confidence,
        verification=result.verification.to_dict() if result.verification else None,
        findings=[
            {"kind": f.kind, "label": f.label, "value": f.value, "source": f.source, "confidence": f.confidence}
            for f in result.findings
        ],
        report=result.report.to_dict() if result.report else None,
        created_at=datetime.now(timezone.utc)
    )