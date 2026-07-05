"""The single source of plan behavior in the API.

Plans are data: the plans table is authoritative, these fallbacks keep
the API working when a row is missing. No other module may define plan
numbers — routes import from here.
"""
from __future__ import annotations

from typing import Any, Optional

# Mirrors api/migrations/002_platform.sql. Workforce limits use the same
# keys as perceptai.workforce.WorkforceLimits so they map 1:1.
PLAN_FALLBACKS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Starter",
        "monthly_executions": 100,
        "limits": {"max_parallel": 2, "max_work_orders": 6,
                   "max_mission_duration_s": 1800, "max_total_cost": 25},
    },
    "builder": {
        "name": "Builder",
        "monthly_executions": 10_000,
        "limits": {"max_parallel": 4, "max_work_orders": 12,
                   "max_mission_duration_s": 3600, "max_total_cost": 100},
    },
    "scale": {
        "name": "Scale",
        "monthly_executions": 999_999,
        "limits": {"max_parallel": 8, "max_work_orders": 24,
                   "max_mission_duration_s": 7200, "max_total_cost": 500},
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_executions": 999_999,
        "limits": {"max_parallel": 16, "max_work_orders": 64,
                   "max_mission_duration_s": 14400, "max_total_cost": 5000},
    },
}

DEFAULT_PLAN = "free"


def get_plan(plan_id: Optional[str], db=None) -> dict[str, Any]:
    """Resolve a plan to {id, name, monthly_executions, limits}.

    Reads the plans table when a client is given; unknown ids and DB
    failures degrade to the fallback table (never crash a request over
    plan metadata).
    """
    pid = (plan_id or DEFAULT_PLAN).strip().lower()
    if db is not None:
        try:
            rows = db.table("plans").select("*").eq("id", pid).execute().data
            if rows:
                row = rows[0]
                fallback = PLAN_FALLBACKS.get(pid, PLAN_FALLBACKS[DEFAULT_PLAN])
                return {
                    "id": pid,
                    "name": row.get("name") or fallback["name"],
                    "monthly_executions": row.get("monthly_executions")
                    or fallback["monthly_executions"],
                    "limits": row.get("limits") or fallback["limits"],
                }
        except Exception:
            pass
    fallback = PLAN_FALLBACKS.get(pid, PLAN_FALLBACKS[DEFAULT_PLAN])
    return {"id": pid if pid in PLAN_FALLBACKS else DEFAULT_PLAN, **fallback}


def monthly_limit(plan_id: Optional[str], db=None) -> int:
    return int(get_plan(plan_id, db)["monthly_executions"])
