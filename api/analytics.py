"""Analytics aggregation (Sprint 2 — Analytics V2).

Pure computation over persisted sessions/missions rows: no schema of its own,
no rollup tables — it derives everything from the source of truth. `build_summary`
does the DB fetch; `compute_summary` is a pure function so it can be unit-tested
with synthetic rows. The response dict is the stable contract shared with the
frontend; the implementation behind it can later move to SQL or a rollup table
without changing that shape.

Tasks (sessions) and missions collapse into one `Run` model:
  outcome  = success | attention | failure
  success  -> COMPLETED (task) / completed (mission)
  attention-> UNVERIFIED (task) / partial (mission)   # acted, not confirmed
  failure  -> FAILED (task) / failed|cancelled (mission)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date
from typing import Any, Optional

# Confidence-bucket edges for the calibration chart.
_CONF_EDGES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]

# Human-friendly labels for the structured failure taxonomy.
FAILURE_LABELS: dict[str, str] = {
    "element_not_found": "Element not found",
    "element_renamed": "UI element changed",
    "window_changed": "Window changed",
    "modal_dialog": "Unexpected dialog",
    "focus_lost": "Focus lost",
    "wrong_app": "Wrong app targeted",
    "app_not_open": "App didn't open",
    "loading": "Slow loading / timing",
    "unverified": "Unverified outcome",
    "specialist_failure": "Specialist failure",
    "mission_error": "Mission error",
    "unknown": "Unclassified",
    "other": "Other",
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


# ------------------------------------------------------------ normalization

def _session_run(row: dict) -> Optional[dict]:
    status = (row.get("status") or "").lower()
    outcome = {
        "completed": "success",
        "unverified": "attention",
        "failed": "failure",
    }.get(status)
    if outcome is None:
        return None  # running/pending — not a terminal run
    result = row.get("result") or {}
    report = (result or {}).get("report") or {}
    verification = (result or {}).get("verification") or {}
    confidence = _num(report.get("confidence"))
    if confidence is None:
        confidence = _num(verification.get("confidence"))
    if confidence is None:
        confidence = _num(result.get("confidence"))
    failure_type = result.get("failure_type")
    if outcome == "attention" and not failure_type:
        failure_type = "unverified"
    return {
        "kind": "task",
        "created_at": _parse_dt(row.get("created_at")),
        "outcome": outcome,
        "claimed_success": status in ("completed", "unverified"),
        "duration_s": _num(row.get("execution_time")),
        "confidence": confidence,
        "verified": bool(verification.get("verified")) if verification else (outcome == "success"),
        "failure_type": failure_type if outcome != "success" else None,
        "cost": 0.0,
    }


def _mission_run(row: dict) -> Optional[dict]:
    status = (row.get("status") or "").lower()
    outcome = {
        "completed": "success",
        "partial": "attention",
        "failed": "failure",
        "cancelled": "failure",
    }.get(status)
    if outcome is None:
        return None
    result = row.get("result") or {}
    metrics = row.get("metrics") or (result or {}).get("metrics") or {}
    failure_type = None
    if outcome != "success":
        failure_type = "specialist_failure" if _num(metrics.get("orders_failed")) else "mission_error"
    return {
        "kind": "mission",
        "created_at": _parse_dt(row.get("created_at")),
        "outcome": outcome,
        "claimed_success": status in ("completed", "partial"),
        "duration_s": _num(row.get("duration_s")),
        "confidence": _num(result.get("confidence")),
        "verified": outcome == "success",
        "failure_type": failure_type,
        "cost": _num(metrics.get("cost_total")) or 0.0,
        "metrics": metrics,
    }


# ------------------------------------------------------------- computation

def compute_summary(
    sessions: list[dict],
    missions: list[dict],
    *,
    days: int,
    kind: str = "all",
    executions_used: int = 0,
    executions_limit: int = 0,
    plan: str = "free",
    now: Optional[datetime] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    runs: list[dict] = []
    if kind in ("all", "task"):
        runs += [r for r in (_session_run(s) for s in sessions) if r]
    if kind in ("all", "mission"):
        runs += [r for r in (_mission_run(m) for m in missions) if r]
    runs = [r for r in runs if r["created_at"] and r["created_at"] >= window_start]

    n = len(runs)
    successes = [r for r in runs if r["outcome"] == "success"]
    attention = [r for r in runs if r["outcome"] == "attention"]
    failures = [r for r in runs if r["outcome"] == "failure"]

    success_rate = round(len(successes) / n, 4) if n else 0.0
    acted = len(successes) + len(attention)
    verification_accuracy = round(len(successes) / acted, 4) if acted else None

    # --- daily outcome timeseries (fill zero days) ---
    day_keys = [(now.date() - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    buckets: dict[date, dict[str, int]] = {
        d: {"success": 0, "attention": 0, "failure": 0} for d in day_keys
    }
    lat_by_day: dict[date, list[float]] = {d: [] for d in day_keys}
    for r in runs:
        d = r["created_at"].date()
        if d in buckets:
            buckets[d][r["outcome"]] += 1
            if r["duration_s"]:
                lat_by_day[d].append(r["duration_s"])
    timeseries = [
        {"date": d.isoformat(), **buckets[d]} for d in day_keys
    ]

    # --- latency ---
    durations = [r["duration_s"] for r in runs if r["duration_s"]]
    latency = {
        "p50_s": round(_percentile(durations, 0.5), 2) if durations else None,
        "p95_s": round(_percentile(durations, 0.95), 2) if durations else None,
        "avg_s": round(sum(durations) / len(durations), 2) if durations else None,
        "series": [
            {"date": d.isoformat(),
             "p50": round(_percentile(lat_by_day[d], 0.5), 2) if lat_by_day[d] else None}
            for d in day_keys
        ],
    }

    # --- calibration (confidence vs actual success), success/failure only ---
    calib_runs = [r for r in runs if r["confidence"] is not None and r["outcome"] in ("success", "failure")]
    conf_buckets = []
    for i in range(len(_CONF_EDGES) - 1):
        lo, hi = _CONF_EDGES[i], _CONF_EDGES[i + 1]
        members = [r for r in calib_runs if lo <= r["confidence"] < hi]
        conf_buckets.append({
            "lo": round(lo, 2),
            "hi": round(min(hi, 1.0), 2),
            "n": len(members),
            "actual_success": round(
                sum(1 for r in members if r["outcome"] == "success") / len(members), 4
            ) if members else None,
        })
    mean_error = (
        round(sum(abs(r["confidence"] - (1.0 if r["outcome"] == "success" else 0.0))
                  for r in calib_runs) / len(calib_runs), 4)
        if calib_runs else None
    )
    calibration = {
        "buckets": conf_buckets,
        "mean_error": mean_error,
        "verification_accuracy": verification_accuracy,
        "sample_size": len(calib_runs),
    }

    # --- failure taxonomy ---
    fail_counts: dict[str, int] = {}
    for r in failures + attention:
        ft = r["failure_type"] or "unknown"
        fail_counts[ft] = fail_counts.get(ft, 0) + 1
    failures_list = sorted(
        ({"type": k, "label": FAILURE_LABELS.get(k, k.replace("_", " ").title()), "count": v}
         for k, v in fail_counts.items()),
        key=lambda x: x["count"], reverse=True,
    )

    # --- missions strip ---
    mission_runs = [r for r in runs if r["kind"] == "mission"]
    mission_block = None
    if mission_runs:
        util: dict[str, list[float]] = {}
        reassignments = duplicates = orders_total = 0
        for r in mission_runs:
            m = r.get("metrics") or {}
            reassignments += int(m.get("reassignments") or 0)
            duplicates += int(m.get("duplicates_cancelled") or 0)
            orders_total += int(m.get("orders_total") or 0)
            for name, rate in (m.get("specialist_utilization") or {}).items():
                util.setdefault(name, []).append(_num(rate) or 0.0)
        mission_block = {
            "count": len(mission_runs),
            "reassignments": reassignments,
            "duplicates_cancelled": duplicates,
            "avg_orders": round(orders_total / len(mission_runs), 1) if mission_runs else 0,
            "cost_total": round(sum(r["cost"] for r in mission_runs), 2),
            "specialist_utilization": {
                k: round(sum(v) / len(v), 3) for k, v in sorted(util.items())
            },
        }

    totals = {
        "runs": n,
        "tasks": sum(1 for r in runs if r["kind"] == "task"),
        "missions": len(mission_runs),
        "succeeded": len(successes),
        "needs_attention": len(attention),
        "failed": len(failures),
        "success_rate": success_rate,
        "verification_rate": round(sum(1 for r in runs if r["verified"]) / n, 4) if n else 0.0,
    }
    cost = {
        "executions_used": executions_used,
        "executions_limit": executions_limit,
        "percentage_used": round((executions_used / executions_limit) * 100, 1) if executions_limit else 0.0,
        "mission_cost_total": mission_block["cost_total"] if mission_block else 0.0,
    }

    summary = {
        "range": {"days": days, "start": window_start.date().isoformat(), "end": now.date().isoformat()},
        "kind": kind,
        "totals": totals,
        "timeseries": timeseries,
        "latency": latency,
        "calibration": calibration,
        "failures": failures_list,
        "cost": cost,
        "missions": mission_block,
    }
    summary["recommendations"] = recommend(summary)
    return summary


# --------------------------------------------------------- recommendations

def _rec(severity: str, title: str, detail: str, metric: str = "") -> dict:
    return {"severity": severity, "title": title, "detail": detail, "metric": metric}


# Concrete, platform-aware advice per structured failure cause.
_FAILURE_ADVICE = {
    "element_not_found": ("UI drift is your top failure cause",
        "The agent couldn't locate target elements. Prefer apps with UI Automation / DOM structure, and consider raising find_retries so transient renders don't fail a run."),
    "element_renamed": ("UI labels are changing under the agent",
        "Elements are being found but renamed between snapshots. Lean on structured sources (UIA/DOM) over OCR text for these targets."),
    "window_changed": ("Windows shift mid-run",
        "The foreground window changes during execution. Keep the target app in front and avoid launching background apps during a run."),
    "modal_dialog": ("Unexpected dialogs interrupt runs",
        "Dialogs are blocking steps. Add a dismissal step for known prompts, or raise max_healing_attempts so recovery can clear them."),
    "focus_lost": ("Focus loss is causing failures",
        "Input is landing in the wrong window. Ensure other apps aren't stealing focus; the runtime re-focuses before input, so this usually means a noisy desktop."),
    "wrong_app": ("The agent targeted the wrong app",
        "Disambiguate app names in your instructions (use exact titles), so the planner resolves the right window."),
    "app_not_open": ("Apps aren't launching",
        "Launch is failing. Verify the app name resolves via PATH or App Paths on this host, or open it before the run."),
    "loading": ("Timing-related failures",
        "Steps run before the UI settles. Increase settle delays for slow apps in EngineConfig."),
    "unverified": ("Runs finish but can't be verified",
        "Many runs complete their steps but verification can't confirm the goal. Add explicit completion criteria to your instruction so the outcome is checkable."),
    "specialist_failure": ("Specialists are failing mid-mission",
        "Individual work orders are failing. Review specialist health and capability routing in the workforce roster."),
}


def recommend(s: dict) -> list[dict]:
    """Turn the computed summary into ranked, actionable guidance —
    'what should I do next' rather than just 'what happened'."""
    recs: list[dict] = []
    totals = s["totals"]
    n = totals["runs"]

    if n < 3:
        return [_rec("info", "Run more to unlock insights",
                     "Analytics and recommendations sharpen after a handful of runs. Run a few tasks or missions to establish a baseline.",
                     "sample size")]

    # Top failure cause → targeted advice.
    if s["failures"]:
        top = s["failures"][0]
        share = top["count"] / n
        advice = _FAILURE_ADVICE.get(top["type"])
        if advice and share >= 0.15:
            title, detail = advice
            recs.append(_rec("high" if share >= 0.35 else "medium", title, detail,
                             f'{top["label"]} · {top["count"]} of {n} runs'))

    # Verification accuracy: agent thinks it's done but it isn't.
    va = s["calibration"]["verification_accuracy"]
    if va is not None and (totals["succeeded"] + totals["needs_attention"]) >= 5 and va < 0.7:
        recs.append(_rec("high", "Tighten what 'done' means",
                         "The agent often finishes its steps without independent verification confirming the goal. Add explicit completion criteria, or use mission mode for multi-step goals so outcomes are checked.",
                         f"verification accuracy {round(va * 100)}%"))

    # Calibration quality.
    me = s["calibration"]["mean_error"]
    if me is not None and s["calibration"]["sample_size"] >= 10 and me > 0.25:
        recs.append(_rec("medium", "Confidence is poorly calibrated",
                         "Reported confidence doesn't track real outcomes on this workload. Treat confidence scores with caution and rely on verification for go/no-go decisions.",
                         f"calibration error {round(me, 2)}"))

    # Latency tail.
    p95 = s["latency"]["p95_s"]
    if p95 is not None and p95 > 90:
        recs.append(_rec("medium", "Trim the long-tail latency",
                         "A few runs are very slow. Break large goals into smaller tasks or publish them as workflows so each step is bounded.",
                         f"p95 {p95}s"))

    # Overall success.
    if n >= 5 and totals["success_rate"] < 0.6:
        recs.append(_rec("high", "Overall reliability is low",
                         "Success rate is below 60%. Start from a template, simplify instructions, and address the top failure cause above.",
                         f'success {round(totals["success_rate"] * 100)}%'))

    # Missions: churn.
    mb = s.get("missions")
    if mb and mb["avg_orders"] and mb["reassignments"] / max(mb["count"], 1) >= 1:
        recs.append(_rec("medium", "Missions are reassigning frequently",
                         "Work orders are bouncing between specialists. Review capability routing and specialist health to cut wasted cycles.",
                         f'{mb["reassignments"]} reassignments'))

    # Healthy → positive nudge.
    if not recs:
        recs.append(_rec("info", "Reliability looks strong",
                         "No systemic issues detected. Consider scheduling your best workflows so they run unattended.",
                         f'success {round(totals["success_rate"] * 100)}%'))

    order = {"high": 0, "medium": 1, "info": 2}
    recs.sort(key=lambda r: order.get(r["severity"], 3))
    return recs[:4]


# --------------------------------------------------------------- DB facade

def build_summary(db, user_id: str, days: int, kind: str) -> dict:
    """Fetch this user's terminal runs in-window and aggregate them. Bounded
    row scan (latency is a feature); swap for SQL/rollup later behind this
    same return shape."""
    from datetime import datetime as _dt
    month = _dt.now(timezone.utc).strftime("%Y-%m")

    sessions: list[dict] = []
    missions: list[dict] = []
    if kind in ("all", "task"):
        sessions = db.table("sessions").select(
            "status, execution_time, result, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1000).execute().data or []
    if kind in ("all", "mission"):
        missions = db.table("missions").select(
            "status, duration_s, metrics, result, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1000).execute().data or []

    usage = db.table("usage").select("executions").eq(
        "user_id", user_id).eq("month", month).execute().data
    executions_used = usage[0]["executions"] if usage else 0

    plan_rows = db.table("user_plans").select("plan_id").eq("user_id", user_id).execute().data
    plan_id = plan_rows[0]["plan_id"] if plan_rows else "free"
    from plans import monthly_limit
    executions_limit = monthly_limit(plan_id, db)

    return compute_summary(
        sessions, missions, days=days, kind=kind,
        executions_used=executions_used, executions_limit=executions_limit, plan=plan_id,
    )
