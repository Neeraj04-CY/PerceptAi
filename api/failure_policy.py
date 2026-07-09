"""Failure policy — what the plane does when an unattended run fails.

Policy is data on the workflow schedule (never code):
    schedule.on_failure = {"retries": 0..3, "notify": true}

Deliberately separate from Sprint 4/5 reclaim semantics: reclaim owns
UNCERTAIN state (a runner disappeared — requeue never-started work, dead-letter
mid-execution work), while this module owns HONEST failure (the runtime ran
and reported FAILED). Only honest failures are policy-retryable: a retry is a
fresh, linked session (retry_of) dispatched through the ONE dispatch path,
bounded by the policy and a hard cap. Dead-lettered work is never policy-
retried — progress is unknown and a real-screen task is not idempotent;
verify-before-retry is the documented hardening step.

Everything a human must see lands on the Attention surface; a run that fails
with retries remaining retries silently (that is the point of the policy).
"""
from __future__ import annotations

from typing import Any, Optional

MAX_POLICY_RETRIES = 3  # hard cap — every loop is bounded, policy included


# ------------------------------------------------------------ pure decisions

def failure_policy(workflow: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Normalize schedule.on_failure. Absent/malformed degrades to the safe
    default: no retries, do notify."""
    schedule = (workflow or {}).get("schedule") or {}
    raw = schedule.get("on_failure") or {}
    try:
        retries = max(0, min(MAX_POLICY_RETRIES, int(raw.get("retries", 0))))
    except (TypeError, ValueError):
        retries = 0
    notify = bool(raw.get("notify", True))
    return {"retries": retries, "notify": notify}


def retry_decision(session: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Whether a failed run earns a policy retry — ONE tested source of truth.
    Only scheduled runs are unattended (interactive failures already have an
    operator in the cockpit), and only up to the declared bound."""
    if session.get("origin") != "schedule":
        return {"retry": False, "reason": "not an unattended run"}
    used = int(session.get("retry_count", 0) or 0)
    if used >= policy["retries"]:
        return {"retry": False, "reason": "retries exhausted" if policy["retries"] else "no retries declared"}
    return {"retry": True, "next_retry_count": used + 1}


# ------------------------------------------------------------------- apply

def apply_failure_policy(db, session: dict[str, Any], *,
                         workflow: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Called at every point a run reaches an honest terminal FAILED state
    (runner result report, local scheduled run). Never raises — policy
    handling must not break result persistence. Returns what it decided."""
    from attention import raise_attention
    from orgs import record_audit

    if session.get("origin") != "schedule" or not session.get("workflow_id"):
        return {"retry": False, "notified": False}

    try:
        if workflow is None:
            rows = db.table("workflows").select("*").eq(
                "id", session["workflow_id"]).limit(1).execute().data or []
            workflow = rows[0] if rows else None
        policy = failure_policy(workflow)
        decision = retry_decision(session, policy)

        if decision.get("retry") and workflow is not None:
            from dispatch import dispatch_workflow_run
            from config import config
            result = dispatch_workflow_run(
                db, workflow, allow_local=config.ENABLE_SCHEDULER,
                origin="schedule", retry_of=str(session["id"]),
                retry_count=decision["next_retry_count"])
            record_audit(db, session["org_id"], None, "scheduler", "schedule.retried",
                         workflow.get("name", ""), {
                             "failed_session_id": str(session["id"]),
                             "retry_session_id": result.get("session_id"),
                             "retry": decision["next_retry_count"],
                             "of": policy["retries"]},
                         workspace_id=session.get("workspace_id"))
            if result.get("dispatched"):
                return {"retry": True, "notified": False,
                        "retry_session_id": result.get("session_id")}
            # the retry itself couldn't be dispatched — fall through to notify

        if policy["notify"] and session.get("org_id"):
            name = (workflow or {}).get("name") or "workflow"
            used = int(session.get("retry_count", 0) or 0)
            raise_attention(
                db, session["org_id"], kind="run_failed", ref=str(session["id"]),
                title=f"Scheduled run of '{name}' failed",
                detail={"error": session.get("error"),
                        "retries_used": used, "retries_declared": policy["retries"]},
                workspace_id=session.get("workspace_id"),
                workflow_id=session.get("workflow_id"),
                session_id=str(session["id"]))
            return {"retry": False, "notified": True}
    except Exception:
        pass
    return {"retry": False, "notified": False}
