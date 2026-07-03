"""Wire-format serialization of the canonical event stream.

This is the ONLY place that knows the legacy dashboard SSE schema
(wire format v0). Future consumers (runner protocol, replay) add
their serializers here instead of building events by hand.
"""
from __future__ import annotations

from typing import Optional

from .contracts import TaskResult
from .events import EventType, TaskEvent


def to_legacy_sse(event: TaskEvent) -> Optional[dict]:
    """Map a canonical TaskEvent to the dashboard's SSE dict schema.
    Returns None for events with no legacy representation."""
    p = event.payload

    if event.type == EventType.TASK_STARTED:
        return {"type": "session_start", "instruction": p.get("instruction", ""), "timestamp": event.timestamp}

    if event.type == EventType.PLAN_CREATED:
        return {
            "type": "plan",
            "steps": [
                {
                    "step_number": i + 1,
                    "description": s.get("description", ""),
                    "action": s.get("action", ""),
                    "status": "pending",
                }
                for i, s in enumerate(p.get("steps", []))
            ],
        }

    if event.type == EventType.STEP_STARTED:
        return {
            "type": "step_start",
            "step_number": p.get("step_number", 0),
            "description": p.get("description", ""),
            "action": p.get("action", ""),
        }

    if event.type == EventType.STEP_COMPLETED:
        ok = p.get("status") in ("completed", "healed")
        result: dict = {"success": ok}
        data = p.get("data") or {}
        if data.get("extracted"):
            result["extracted"] = data["extracted"]
        if p.get("error"):
            result["error"] = p["error"]
        return {
            "type": "step_complete",
            "step": {
                "step_number": p.get("step_number", 0),
                "description": p.get("description", ""),
                "action": p.get("action", ""),
                "status": "completed" if ok else "failed",
                "result": result,
                "timestamp": event.timestamp,
                "duration": p.get("duration_s", 0.0),
            },
        }

    if event.type == EventType.REPLANNED:
        return {"type": "replan", "message": f"Replanned {p.get('count', 0)} steps from live screen"}

    if event.type == EventType.HEALING_STARTED:
        return {"type": "log", "message": f"Healing attempt {p.get('attempt', 1)}: {p.get('failed_step', '')}"}

    if event.type == EventType.HEALING_RESULT:
        if p.get("healed"):
            return {"type": "log", "message": f"Healed: {p.get('diagnosis', '')}"}
        return {"type": "log", "message": f"Diagnosis: {p.get('diagnosis', '')}"}

    if event.type == EventType.VERIFICATION:
        return {
            "type": "log",
            "message": f"Verification: verified={p.get('verified')} confidence={p.get('confidence')} — {p.get('reason', '')}",
        }

    if event.type == EventType.LOG:
        return {"type": "log", "message": p.get("message", "")}

    if event.type == EventType.TASK_COMPLETED:
        return {
            "type": "complete",
            "status": p.get("status", ""),
            "execution_time": p.get("duration_s", 0.0),
            "total_steps": p.get("total_steps", 0),
            "verification": p.get("verification"),
        }

    if event.type == EventType.ERROR:
        return {"type": "error", "message": p.get("message", "")}

    return None


def legacy_steps(result: TaskResult) -> list[dict]:
    """Serialize TaskResult steps into the dashboard's session-steps schema."""
    steps = []
    for r in result.steps:
        payload: dict = {"success": r.ok, **r.data}
        if r.error:
            payload["error"] = r.error
        steps.append(
            {
                "step_number": r.index,
                "description": r.step.description,
                "action": r.step.action.value,
                "status": "completed" if r.ok else "failed",
                "result": payload,
                "timestamp": r.started_at,
                "duration": r.duration_s,
            }
        )
    return steps
