"""Scheduled workflow dispatch — the plane-side clock, nothing more.

Schedules are data on the workflow row ({enabled, interval_minutes,
next_run_at, target, on_failure}); this loop claims due workflows and hands
each one to the ONE dispatch path (dispatch.dispatch_workflow_run). The
scheduler never executes anything itself: runner-targeted runs are enqueued
into the Sprint 4 work queue, and the explicit `this_machine` target runs
through the same local executor as interactive runs — only on hosts that
opted in with ENABLE_SCHEDULER, because that controls THIS host's desktop.

The loop itself is safe everywhere (DB reads/writes only), so it always
runs — a cloud control plane dispatches scheduled work to the fleet with no
flag. Single-process by design, like relay.py and control_registry.py; the
claim-before-dispatch update on next_run_at keeps a crashed cycle from tight-
looping and keeps concurrent processes mostly benign.

Scheduled runs are task-mode only for now: mission workflows need an
interactive approver and per-run limits, so they stay on-demand.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from config import config
from database import get_service_db
from dispatch import dispatch_workflow_run
from orgs import record_audit

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

    dispatched = 0
    for workflow in rows:
        schedule = workflow.get("schedule") or {}
        if not schedule.get("enabled"):
            continue
        next_run = schedule.get("next_run_at")
        if next_run and next_run > now.isoformat():
            continue

        # Claim before dispatching so a crash can't produce a tight retry loop.
        interval = max(MIN_INTERVAL_MIN, int(schedule.get("interval_minutes") or 1440))
        schedule["next_run_at"] = (now + timedelta(minutes=interval)).isoformat()
        schedule["last_run_at"] = now.isoformat()
        db.table("workflows").update({"schedule": schedule}).eq(
            "id", workflow["id"]).execute()

        if workflow.get("mode") == "mission":
            record_audit(db, workflow["org_id"], None, "scheduler",
                         "schedule.skipped", workflow["name"],
                         {"reason": "mission workflows run on demand"})
            continue

        dispatch_workflow_run(db, workflow, allow_local=config.ENABLE_SCHEDULER)
        dispatched += 1
    return dispatched
