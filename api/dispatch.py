"""Workflow dispatch — the ONE path from "this workflow should run now" to an
execution, used by the scheduler and by failure-policy retries.

A dispatch either enqueues a session into the Sprint 4 work queue (a runner
claims and executes it) or, for the explicit `this_machine` target, runs it
through the same local executor interactive runs use — gated by
ENABLE_SCHEDULER because that controls THIS host's real desktop. The decision
is pure and unit-tested; the DB/executor calls stay thin around it.

Targets are data on the workflow schedule (never code):
    schedule.target = {"kind": "this_machine" | "runner" | "any_available",
                       "runner_id": "..." (kind == "runner" only)}
A schedule without a target means `this_machine` — the exact pre-Sprint-8
behavior, so existing rows keep working untouched.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from templates import render_instruction

DEFAULT_TARGET = {"kind": "this_machine"}


# ------------------------------------------------------------ pure decisions

def schedule_target(workflow: dict[str, Any]) -> dict[str, Any]:
    """Normalize the schedule's execution target. Unknown shapes degrade to
    the safe default (this_machine, which never runs unless the host opted in)."""
    schedule = workflow.get("schedule") or {}
    target = schedule.get("target") or {}
    kind = str(target.get("kind", "") or "")
    if kind == "runner" and target.get("runner_id"):
        return {"kind": "runner", "runner_id": str(target["runner_id"])}
    if kind == "any_available":
        return {"kind": "any_available"}
    return dict(DEFAULT_TARGET)


def dispatch_decision(target: dict[str, Any], *, allow_local: bool,
                      runners: list[dict[str, Any]]) -> dict[str, Any]:
    """What to do for a due run — ONE tested source of truth.

    Returns {"action": "enqueue" | "run_local" | "blocked", ...} plus an
    optional "warning" when the work is enqueued but no eligible runner is
    online (the queue holds it; the operator should know). `runners` carries
    derived statuses (runners.public_runner rows).
    """
    kind = target.get("kind", "this_machine")
    if kind == "this_machine":
        if not allow_local:
            return {"action": "blocked",
                    "reason": ("workflow targets this machine but the host does not "
                               "allow scheduled desktop execution (set ENABLE_SCHEDULER "
                               "or retarget the schedule to a runner)")}
        return {"action": "run_local"}
    if kind == "runner":
        runner_id = str(target.get("runner_id", ""))
        match = next((r for r in runners if str(r.get("id")) == runner_id), None)
        if match is None:
            return {"action": "blocked",
                    "reason": "the schedule's pinned runner no longer exists — retarget it"}
        decision: dict[str, Any] = {"action": "enqueue", "target_runner_id": runner_id}
        if match.get("status") == "offline":
            decision["warning"] = f"pinned runner '{match.get('name', runner_id)}' is offline; the run will wait in the queue"
        return decision
    # any_available
    decision = {"action": "enqueue", "target_runner_id": None}
    if not any(r.get("status") in ("online", "busy") for r in runners):
        decision["warning"] = "no runner is online; the run will wait in the queue"
    return decision


# ------------------------------------------------------------------ dispatch

def dispatch_workflow_run(db, workflow: dict[str, Any], *,
                          allow_local: bool,
                          origin: str = "schedule",
                          retry_of: Optional[str] = None,
                          retry_count: int = 0) -> dict[str, Any]:
    """Render + dispatch one run of a workflow. Never raises: a run that
    cannot be dispatched is recorded honestly (audit + attention) and reported
    in the returned summary. Returns {"dispatched": bool, "session_id": ...,
    "action": ..., "reason"/"warning": ...}.
    """
    import runners as runner_svc
    from attention import raise_attention
    from orgs import record_audit

    org_id = workflow["org_id"]
    workspace_id = workflow.get("workspace_id")

    try:
        instruction = render_instruction(
            workflow.get("instruction", ""),
            workflow.get("variables") or [], {})
        if not instruction:
            raise ValueError("workflow renders to an empty instruction")
    except ValueError as e:
        record_audit(db, org_id, None, "scheduler", "schedule.blocked",
                     workflow["name"], {"reason": str(e)}, workspace_id=workspace_id)
        raise_attention(db, org_id, kind="schedule_blocked", ref=str(workflow["id"]),
                        title=f"Scheduled workflow '{workflow['name']}' cannot run",
                        detail={"reason": str(e)}, workspace_id=workspace_id,
                        workflow_id=workflow["id"])
        return {"dispatched": False, "action": "blocked", "reason": str(e)}

    target = schedule_target(workflow)
    fleet = runner_svc.list_runners(db, org_id) if target["kind"] != "this_machine" else []
    decision = dispatch_decision(target, allow_local=allow_local, runners=fleet)

    if decision["action"] == "blocked":
        record_audit(db, org_id, None, "scheduler", "schedule.blocked",
                     workflow["name"], {"reason": decision["reason"]},
                     workspace_id=workspace_id)
        raise_attention(db, org_id, kind="schedule_blocked", ref=str(workflow["id"]),
                        title=f"Scheduled workflow '{workflow['name']}' cannot run",
                        detail={"reason": decision["reason"]}, workspace_id=workspace_id,
                        workflow_id=workflow["id"])
        return {"dispatched": False, **decision}

    if decision["action"] == "enqueue":
        session = runner_svc.enqueue_session(
            db, user_id=workflow["created_by"], org_id=org_id,
            instruction=instruction, workspace_id=workspace_id,
            workflow_id=workflow["id"], origin=origin,
            retry_of=retry_of, retry_count=retry_count,
            target_runner_id=decision.get("target_runner_id"),
        )
        record_audit(db, org_id, None, "scheduler", "schedule.dispatched",
                     workflow["name"], {"session_id": session["id"],
                                        "target": target,
                                        "retry_of": retry_of},
                     workspace_id=workspace_id)
        if decision.get("warning"):
            raise_attention(db, org_id, kind="no_runner", ref=str(workflow["id"]),
                            title=f"'{workflow['name']}' is queued with no runner online",
                            detail={"warning": decision["warning"]},
                            workspace_id=workspace_id, workflow_id=workflow["id"],
                            session_id=session["id"])
        return {"dispatched": True, "session_id": session["id"], **decision}

    # run_local — the explicit this_machine target on an opted-in host. Same
    # executor as interactive local runs; the scheduler itself never executes.
    session_id = _run_local_session(db, workflow, instruction,
                                    origin=origin, retry_of=retry_of,
                                    retry_count=retry_count)
    return {"dispatched": True, "session_id": session_id, "action": "run_local"}


def _run_local_session(db, workflow: dict[str, Any], instruction: str, *,
                       origin: str, retry_of: Optional[str], retry_count: int) -> str:
    """Execute on THIS host through the same executor as interactive runs,
    then persist the result and apply the failure policy. Only reachable via
    the explicit this_machine target with ENABLE_SCHEDULER set."""
    from executor import execute_task_stream
    from events_store import EventBuffer
    from failure_policy import apply_failure_policy
    from orgs import record_audit
    from routes.execute_routes import increment_usage
    from secrets_resolver import build_local_resolver

    session_id = str(uuid.uuid4())
    row = {
        "id": session_id,
        "user_id": workflow["created_by"],
        "org_id": workflow["org_id"],
        "workspace_id": workflow.get("workspace_id"),
        "workflow_id": workflow["id"],
        "instruction": instruction,
        "status": "running",
        "origin": origin,
        "retry_of": retry_of,
        "retry_count": retry_count,
    }
    db.table("sessions").insert({k: v for k, v in row.items() if v is not None}).execute()

    secrets = build_local_resolver(db, workflow.get("org_id"), workflow.get("workspace_id"))
    final = {"status": "failed", "steps": [], "result": None,
             "error": None, "execution_time": 0.0, "events": []}
    for item in execute_task_stream(instruction, secrets=secrets):
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
    record_audit(db, workflow["org_id"], None, "scheduler", "schedule.executed",
                 workflow["name"], {"session_id": session_id, "status": final["status"]},
                 workspace_id=workflow.get("workspace_id"))

    if final["status"] == "failed":
        session = {**row, "status": "failed", "error": final["error"]}
        apply_failure_policy(db, session, workflow=workflow)
    return session_id
