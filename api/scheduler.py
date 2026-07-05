"""Scheduled workflow execution.

Schedules are data on the workflow row ({enabled, interval_minutes,
next_run_at}); this loop claims due workflows and runs them through the
same executor as interactive runs. Execution controls THIS host's
desktop, so the loop only starts when ENABLE_SCHEDULER is set — the
long-term home for this is the remote runner, not the API process.

Scheduled runs are task-mode only for now: mission workflows need an
interactive approver and per-run limits, so they stay on-demand.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from database import get_service_db
from events_store import EventBuffer
from orgs import record_audit
from templates import render_instruction

POLL_S = 60
MIN_INTERVAL_MIN = 5


async def scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_due_workflows)
        except Exception:
            pass  # a bad cycle must not kill the loop; next poll retries
        await asyncio.sleep(POLL_S)


def run_due_workflows() -> int:
    db = get_service_db()
    now = datetime.now(timezone.utc)
    try:
        rows = db.table("workflows").select("*").eq(
            "status", "published").not_.is_("schedule", "null").execute().data or []
    except Exception:
        return 0

    ran = 0
    for workflow in rows:
        schedule = workflow.get("schedule") or {}
        if not schedule.get("enabled"):
            continue
        next_run = schedule.get("next_run_at")
        if next_run and next_run > now.isoformat():
            continue

        # Claim before running so a crash can't produce a tight retry loop.
        interval = max(MIN_INTERVAL_MIN, int(schedule.get("interval_minutes") or 1440))
        schedule["next_run_at"] = (now + timedelta(minutes=interval)).isoformat()
        schedule["last_run_at"] = now.isoformat()
        db.table("workflows").update({"schedule": schedule}).eq(
            "id", workflow["id"]).execute()

        _run_workflow(db, workflow)
        ran += 1
    return ran


def _run_workflow(db, workflow: dict) -> None:
    from executor import execute_task_stream
    from routes.execute_routes import increment_usage

    if workflow.get("mode") == "mission":
        record_audit(db, workflow["org_id"], None, "scheduler",
                     "schedule.skipped", workflow["name"],
                     {"reason": "mission workflows run on demand"})
        return
    try:
        instruction = render_instruction(
            workflow.get("instruction", ""),
            workflow.get("variables") or [], {})
    except ValueError as e:
        record_audit(db, workflow["org_id"], None, "scheduler",
                     "schedule.skipped", workflow["name"], {"reason": str(e)})
        return

    session_id = str(uuid.uuid4())
    db.table("sessions").insert({
        "id": session_id,
        "user_id": workflow["created_by"],
        "org_id": workflow["org_id"],
        "workspace_id": workflow.get("workspace_id"),
        "instruction": instruction,
        "status": "running",
    }).execute()

    final = {"status": "failed", "steps": [], "result": None,
             "error": None, "execution_time": 0.0, "events": []}
    for item in execute_task_stream(instruction):
        if item.get("type") == "_result":
            final.update({k: item.get(k, final[k]) for k in final})
        elif item.get("type") == "error":
            final["error"] = item.get("message")

    db.table("sessions").update({
        "status": final["status"],
        "steps": final["steps"],
        "result": final["result"],
        "error": final["error"],
        "execution_time": final["execution_time"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()

    buffer = EventBuffer()
    for event in final["events"]:
        buffer.collect(event)
    buffer.flush(db, "session", session_id)
    increment_usage(workflow["created_by"], session_id)
    record_audit(db, workflow["org_id"], None, "scheduler",
                 "schedule.executed", workflow["name"],
                 {"session_id": session_id, "status": final["status"]},
                 workspace_id=workflow.get("workspace_id"))
