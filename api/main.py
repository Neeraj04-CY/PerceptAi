from fastapi import FastAPI, Request, HTTPException, Header
import traceback
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import asyncio
import threading
import queue
import json
import uuid
from routes.auth_routes import router as auth_router
from routes.execute_routes import router as execute_router
from routes.dashboard_routes import router as dashboard_router
from routes.keys_routes import router as keys_router
from models import ExecuteRequest
from database import get_service_db

app = FastAPI(
    title="PerceptAI API",
    description="Universal perception layer for AI agents",
    version="0.1.1"
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
    """SSE streaming execution endpoint"""
    from routes.execute_routes import validate_api_key, check_usage_limit, increment_usage
    from executor import execute_task_stream

    key_data = validate_api_key(x_api_key)
    user_id = key_data["user_id"]
    plan_id = key_data.get("plan_id", "free")

    if not check_usage_limit(user_id, plan_id):
        raise HTTPException(429, "Monthly execution limit reached")

    session_id = str(uuid.uuid4())
    db = get_service_db()
    db.table("sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "api_key_id": key_data["id"],
        "instruction": body.instruction,
        "status": "running"
    }).execute()

    result_queue: queue.Queue = queue.Queue()

    def run_executor():
        try:
            for event in execute_task_stream(body.instruction):
                result_queue.put(event)
        except Exception as e:
            result_queue.put({"type": "error", "message": str(e)})
        finally:
            result_queue.put(None)

    thread = threading.Thread(target=run_executor, daemon=True)
    thread.start()

    async def generate():
        yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id})}\n\n"
        yield f"data: {json.dumps({'type': 'log', 'message': 'Runtime connected'})}\n\n"

        all_steps = []
        final_status = "completed"
        execution_time = 0.0
        final_result = None
        final_error = None

        while True:
            try:
                event = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: result_queue.get(timeout=0.1)
                )
            except queue.Empty:
                yield ": keepalive\n\n"
                continue

            if event is None:
                break

            # Internal terminal marker: persist, never forward to clients.
            if event.get("type") == "_result":
                final_result = event.get("result")
                all_steps = event.get("steps") or all_steps
                final_status = event.get("status", final_status)
                execution_time = event.get("execution_time", execution_time)
                final_error = event.get("error")
                continue

            yield f"data: {json.dumps(event)}\n\n"

            if event.get("type") == "step_complete":
                all_steps.append(event["step"])
            if event.get("type") == "complete":
                final_status = event.get("status", "completed")
                execution_time = event.get("execution_time", 0)
            if event.get("type") == "error":
                final_status = "failed"
                final_error = event.get("message")

        db.table("sessions").update({
            "status": final_status,
            "steps": all_steps,
            "result": final_result,
            "error": final_error,
            "execution_time": execution_time,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", session_id).execute()

        increment_usage(user_id, session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Connection": "keep-alive",
        }
    )

@app.get("/")
async def root():
    return {
        "name": "PerceptAI API",
        "version": "0.1.1",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"} 

