"""Analytics V2 aggregation tests (Sprint 2). Pure computation over synthetic
session/mission rows — no Supabase, no network."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from analytics import compute_summary, recommend  # noqa: E402

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def _session(status, hours_ago=1, conf=None, failure_type=None, dur=10.0, verified=None):
    result = {"failure_type": failure_type}
    if conf is not None:
        result["report"] = {"confidence": conf}
    if verified is not None:
        result["verification"] = {"verified": verified, "confidence": conf or 0.0}
    return {
        "status": status,
        "execution_time": dur,
        "result": result,
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


def test_outcome_bands_and_totals():
    sessions = [
        _session("completed", conf=0.9, verified=True),
        _session("completed", conf=0.8, verified=True),
        _session("unverified", conf=0.6, verified=False),
        _session("failed", conf=0.7, failure_type="element_not_found"),
    ]
    s = compute_summary(sessions, [], days=30, now=NOW)
    assert s["totals"]["runs"] == 4
    assert s["totals"]["succeeded"] == 2
    assert s["totals"]["needs_attention"] == 1
    assert s["totals"]["failed"] == 1
    assert s["totals"]["success_rate"] == 0.5
    # verification accuracy = success / (success + attention) = 2/3
    assert round(s["calibration"]["verification_accuracy"], 2) == 0.67


def test_timeseries_fills_all_days():
    s = compute_summary([_session("completed", conf=0.9, verified=True)], [], days=7, now=NOW)
    assert len(s["timeseries"]) == 7
    assert s["timeseries"][-1]["success"] == 1  # today


def test_window_excludes_old_runs():
    old = _session("completed", hours_ago=24 * 40, conf=0.9, verified=True)
    recent = _session("completed", hours_ago=2, conf=0.9, verified=True)
    s = compute_summary([old, recent], [], days=30, now=NOW)
    assert s["totals"]["runs"] == 1  # the 40-day-old run is outside the 30d window


def test_calibration_buckets_and_error():
    # Overconfident: high confidence but a failure.
    sessions = [
        _session("completed", conf=0.9, verified=True),   # bucket 0.8-1.0, success
        _session("failed", conf=0.9, failure_type="loading"),  # bucket 0.8-1.0, failure
    ]
    s = compute_summary(sessions, [], days=30, now=NOW)
    top_bucket = s["calibration"]["buckets"][-1]
    assert top_bucket["n"] == 2
    assert top_bucket["actual_success"] == 0.5
    # mean error = (|0.9-1| + |0.9-0|)/2 = (0.1 + 0.9)/2 = 0.5
    assert s["calibration"]["mean_error"] == 0.5


def test_failure_taxonomy_ranked_with_labels():
    sessions = [
        _session("failed", failure_type="element_not_found"),
        _session("failed", failure_type="element_not_found"),
        _session("failed", failure_type="modal_dialog"),
        _session("unverified"),  # -> classified as "unverified"
    ]
    s = compute_summary(sessions, [], days=30, now=NOW)
    top = s["failures"][0]
    assert top["type"] == "element_not_found"
    assert top["count"] == 2
    assert top["label"] == "Element not found"


def test_missions_unified_and_strip():
    missions = [{
        "status": "partial",
        "duration_s": 120.0,
        "metrics": {"orders_total": 6, "orders_failed": 1, "reassignments": 2,
                    "duplicates_cancelled": 1, "cost_total": 20.0,
                    "specialist_utilization": {"browser": 0.8}},
        "result": {"confidence": 0.7},
        "created_at": (NOW - timedelta(hours=3)).isoformat(),
    }]
    s = compute_summary([], missions, days=30, now=NOW, kind="all")
    assert s["totals"]["missions"] == 1
    assert s["totals"]["needs_attention"] == 1  # partial -> attention
    assert s["missions"]["reassignments"] == 2
    assert s["missions"]["specialist_utilization"]["browser"] == 0.8
    # partial mission has a structured failure cause
    assert s["failures"][0]["type"] == "specialist_failure"


def test_kind_filter_isolates_tasks():
    sessions = [_session("completed", conf=0.9, verified=True)]
    missions = [{"status": "completed", "duration_s": 30, "metrics": {}, "result": {"confidence": 0.9},
                 "created_at": (NOW - timedelta(hours=1)).isoformat()}]
    s = compute_summary(sessions, missions, days=30, now=NOW, kind="task")
    assert s["totals"]["missions"] == 0
    assert s["totals"]["tasks"] == 1


def test_recommendation_targets_top_failure():
    sessions = [_session("failed", conf=0.8, failure_type="element_not_found") for _ in range(4)]
    sessions += [_session("completed", conf=0.9, verified=True) for _ in range(2)]
    s = compute_summary(sessions, [], days=30, now=NOW)
    recs = s["recommendations"]
    assert any("UI drift" in r["title"] for r in recs)
    assert recs[0]["severity"] in ("high", "medium")


def test_recommendation_low_sample():
    s = compute_summary([_session("completed", conf=0.9, verified=True)], [], days=30, now=NOW)
    assert s["recommendations"][0]["severity"] == "info"
    assert "Run more" in s["recommendations"][0]["title"]


def test_recommendation_healthy_positive():
    sessions = [_session("completed", conf=0.85, verified=True, dur=8.0) for _ in range(8)]
    s = compute_summary(sessions, [], days=30, now=NOW)
    recs = s["recommendations"]
    assert recs[0]["severity"] == "info"
    assert "strong" in recs[0]["title"].lower()


def test_empty_is_safe():
    s = compute_summary([], [], days=30, now=NOW)
    assert s["totals"]["runs"] == 0
    assert s["calibration"]["mean_error"] is None
    assert s["latency"]["p50_s"] is None
    assert s["missions"] is None
    assert len(s["timeseries"]) == 30
