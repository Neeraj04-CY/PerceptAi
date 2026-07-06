import asyncio
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from config import config
from database import get_service_db
from events_store import EventBuffer
from models import ExecuteRequest
from routes.analytics_routes import router as analytics_router
from routes.approval_routes import router as approval_router
from routes.auth_routes import router as auth_router
from routes.dashboard_routes import router as dashboard_router
from routes.execute_routes import router as execute_router
from routes.keys_routes import router as keys_router
from routes.mission_routes import router as mission_router
from routes.org_routes import router as org_router
from routes.platform_routes import router as platform_router
from routes.workflow_routes import router as workflow_router
from sse import KEEPALIVE, SSE_HEADERS, athread_iter, sse

app = FastAPI(
    title="PerceptAI API",
    description="The AI workforce platform: perception-driven automation, "
                "missions, workflows and organizational controls.",
    version="0.2.0",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(execute_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")
app.include_router(org_router, prefix="/api/v1")
app.include_router(mission_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(approval_router, prefix="/api/v1")
app.include_router(platform_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.on_event("startup")
async def start_scheduler():
    if config.ENABLE_SCHEDULER:
        from scheduler import scheduler_loop
        asyncio.create_task(scheduler_loop())


@app.get("/api/v1/screenshot")
async def get_screenshot():
    """Return the most recent perception screenshot."""
    from executor import latest_screenshot_path
    screenshot_path = latest_screenshot_path()
    if screenshot_path is not None and screenshot_path.exists():
        return Response(
            content=screenshot_path.read_bytes(),
            media_type="image/png",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )
    return Response(status_code=204)


@app.post("/api/v1/execute/stream")
async def execute_stream(
    body: ExecuteRequest,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """SSE streaming execution endpoint (legacy wire format v0)."""
    from routes.execute_routes import validate_api_key, check_usage_limit, increment_usage
    from executor import execute_task_stream

    key_data = validate_api_key(x_api_key)
    user_id = key_data["user_id"]
    plan_id = key_data.get("plan_id", "free")

    if not check_usage_limit(user_id, plan_id):
        raise HTTPException(429, "Monthly execution limit reached")

    session_id = str(uuid.uuid4())
    db = get_service_db()
    row = {
        "id": session_id,
        "user_id": user_id,
        "api_key_id": key_data["id"],
        "instruction": body.instruction,
        "status": "running",
    }
    from orgs import session_scope
    scope = session_scope(db, user_id, body.workspace_id, body.workflow_id)
    try:
        db.table("sessions").insert({**row, **scope}).execute()
    except Exception:
        db.table("sessions").insert(row).execute()

    async def generate():
        yield sse({"type": "session_id", "session_id": session_id})
        yield sse({"type": "log", "message": "Runtime connected"})

        all_steps: list = []
        final = {"status": "completed", "execution_time": 0.0,
                 "result": None, "error": None, "events": []}

        async for event in athread_iter(execute_task_stream(body.instruction)):
            if event is None:
                yield KEEPALIVE
                continue

            # Internal terminal marker: persist, never forward to clients.
            if event.get("type") == "_result":
                final["result"] = event.get("result")
                all_steps = event.get("steps") or all_steps
                final["status"] = event.get("status", final["status"])
                final["execution_time"] = event.get("execution_time",
                                                    final["execution_time"])
                final["error"] = event.get("error")
                final["events"] = event.get("events") or []
                continue

            yield sse(event)

            if event.get("type") == "step_complete":
                all_steps.append(event["step"])
            if event.get("type") == "complete":
                final["status"] = event.get("status", "completed")
                final["execution_time"] = event.get("execution_time", 0)
            if event.get("type") == "error":
                final["status"] = "failed"
                final["error"] = event.get("message")

        db.table("sessions").update({
            "status": final["status"],
            "steps": all_steps,
            "result": final["result"],
            "error": final["error"],
            "execution_time": final["execution_time"],
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", session_id).execute()

        buffer = EventBuffer()
        for event in final["events"]:
            buffer.collect(event)
        buffer.flush(db, "session", session_id)

        increment_usage(user_id, session_id)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers=SSE_HEADERS)


@app.get("/")
async def root():
    return {
        "name": "PerceptAI API",
        "version": "0.2.0",
        "status": "operational",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
