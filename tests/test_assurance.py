"""Chapter XIII — Workflow Assurance: the measured, verified reliability of a
workflow and its evidence-backed autonomy verdict.

The whole product claim rests on this number meaning something, so the math is
pinned hard: verified (not "didn't throw") success, honest calibration, and an
autonomy policy that is conservative and self-explaining.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import assurance as a  # noqa: E402


def _run(status, confidence=None, failure_type=None, error=None, duration=10.0):
    result = {}
    if confidence is not None:
        result["verification"] = {"verified": status == "completed", "confidence": confidence}
    if failure_type:
        result["failure_type"] = failure_type
    return {"status": status, "error": error, "execution_time": duration,
            "result": result or None}


def _many(status, n, **kw):
    return [_run(status, **kw) for _ in range(n)]


# ------------------------------------------------------- verified success rate

def test_success_rate_counts_verified_completion_not_just_no_error():
    # 8 verified completions, 2 failed -> 80% VERIFIED success.
    sessions = _many("completed", 8, confidence=0.9) + _many("failed", 2, confidence=0.3)
    r = a.compute_assurance(sessions)
    assert r["sample_size"] == 10
    assert r["verified_success_rate"] == 0.8
    assert r["completed"] == 8 and r["failed"] == 2


def test_unverified_runs_do_not_count_as_success():
    # 'unverified' means we could NOT confirm the outcome — it is not a success.
    sessions = _many("completed", 5, confidence=0.9) + _many("unverified", 5, confidence=0.5)
    r = a.compute_assurance(sessions)
    assert r["verified_success_rate"] == 0.5
    assert r["unverified"] == 5


def test_non_terminal_runs_are_ignored():
    sessions = _many("completed", 3, confidence=0.9) + [_run("running"), _run("queued")]
    assert a.compute_assurance(sessions)["sample_size"] == 3


def test_empty_history_is_honest():
    r = a.compute_assurance([])
    assert r["sample_size"] == 0 and r["verified_success_rate"] == 0.0
    assert r["autonomy"]["tier"] == a.INSUFFICIENT


# ------------------------------------------------------------- calibration

def test_calibration_error_is_low_when_confidence_matches_reality():
    # Confident (0.95) AND correct (completed) -> tiny error.
    r = a.compute_assurance(_many("completed", 10, confidence=0.95))
    assert r["calibration_error"] == 0.05
    assert r["calibration_samples"] == 10


def test_calibration_error_is_high_for_a_confident_liar():
    # 95% confident but actually FAILED every time -> error near 0.95.
    r = a.compute_assurance(_many("failed", 10, confidence=0.95))
    assert r["calibration_error"] == 0.95


def test_calibration_is_none_without_reported_confidence():
    r = a.compute_assurance(_many("completed", 10))  # no confidence reported
    assert r["calibration_error"] is None
    # Missing calibration must not, by itself, block a strong track record.
    assert r["autonomy"]["tier"] in (a.READY, a.SUPERVISED)


def test_report_confidence_is_used_when_verification_absent():
    s = {"status": "completed", "result": {"report": {"confidence": 0.8}}}
    r = a.compute_assurance([s] * 5)
    assert r["calibration_samples"] == 5


# --------------------------------------------------------- failure taxonomy

def test_failure_taxonomy_groups_by_typed_reason_sorted():
    sessions = (_many("completed", 5, confidence=0.9)
                + _many("failed", 3, failure_type="loading")
                + _many("failed", 1, failure_type="desktop_unavailable"))
    tax = a.compute_assurance(sessions)["failure_taxonomy"]
    assert tax[0] == {"type": "loading", "count": 3}
    assert {"type": "desktop_unavailable", "count": 1} in tax


def test_taxonomy_falls_back_to_error_text_buckets():
    sessions = [_run("failed", error="the entry screen never loaded"),
                _run("failed", error="workstation is locked; no screen")]
    tax = {t["type"]: t["count"] for t in a.compute_assurance(sessions)["failure_taxonomy"]}
    assert tax.get("loading") == 1 and tax.get("desktop_unavailable") == 1


# ---------------------------------------------------- autonomy verdict (policy)

def test_insufficient_history_asks_for_more_runs():
    r = a.compute_assurance(_many("completed", 3, confidence=0.95))
    v = r["autonomy"]
    assert v["tier"] == a.INSUFFICIENT
    assert "2 more" in v["next"]   # 5 - 3


def test_earns_unattended_only_with_volume_success_and_calibration():
    r = a.compute_assurance(_many("completed", 22, confidence=0.95))
    v = r["autonomy"]
    assert v["tier"] == a.READY
    assert "unattended" in v["headline"].lower()
    assert "100%" in v["reason"]


def test_strong_but_thin_history_is_supervised_not_ready():
    # 90%+ success but only 10 runs -> supervised, and it says what's missing.
    sessions = _many("completed", 9, confidence=0.92) + _many("failed", 1, confidence=0.2)
    v = a.compute_assurance(sessions)["autonomy"]
    assert v["tier"] == a.SUPERVISED
    assert "more clean runs" in v["next"]


def test_a_confident_liar_is_never_granted_autonomy():
    # 20 runs, 95% verified success, BUT terrible calibration (overconfident on
    # the failures) -> held back from unattended despite the success rate.
    sessions = (_many("completed", 19, confidence=0.6)   # correct but underconfident
                + _many("failed", 1, confidence=0.99))    # wrong AND overconfident
    r = a.compute_assurance(sessions)
    assert r["verified_success_rate"] == 0.95
    assert r["calibration_error"] > a.READY_MAX_CALIBRATION_ERROR
    assert r["autonomy"]["tier"] == a.SUPERVISED   # calibration gap keeps it supervised


def test_low_success_keeps_a_human_in_the_loop():
    sessions = _many("completed", 4, confidence=0.5) + _many("failed", 6, failure_type="loading")
    v = a.compute_assurance(sessions)["autonomy"]
    assert v["tier"] == a.IN_THE_LOOP
    assert "below the bar" in v["reason"]


def test_every_verdict_explains_itself_and_what_would_change_it():
    for sessions in (
        _many("completed", 3, confidence=0.9),          # insufficient
        _many("completed", 9, confidence=0.9) + _many("failed", 1),  # supervised
        _many("completed", 22, confidence=0.95),        # ready
        _many("failed", 8, failure_type="loading"),     # in the loop
    ):
        v = a.compute_assurance(sessions)["autonomy"]
        assert v["headline"] and v["reason"] and v["next"]


# ---------------------------------------------------- fleet autonomy posture

def _wf(wid, name, sessions):
    return {"id": wid, "name": name, "sessions": sessions}


def test_fleet_posture_rolls_workflows_into_tiers():
    fleet = [
        _wf("a", "Invoices", _many("completed", 22, confidence=0.95)),   # ready
        _wf("b", "CRM", _many("completed", 9, confidence=0.9) + _many("failed", 1)),  # supervised
        _wf("c", "Recon", _many("failed", 8, failure_type="loading")),   # in the loop
        _wf("d", "New wf", _many("completed", 2, confidence=0.9)),       # insufficient
    ]
    p = a.fleet_posture(fleet)
    assert p["total_workflows"] == 4
    assert p["by_tier"][a.READY] == 1
    assert p["by_tier"][a.SUPERVISED] == 1
    assert p["by_tier"][a.IN_THE_LOOP] == 1
    assert p["by_tier"][a.INSUFFICIENT] == 1
    assert p["earned_autonomy"] == 1


def test_fleet_posture_flags_confident_liars_at_scale():
    # High verified success but poor calibration -> flagged, not trusted.
    liar = _many("completed", 19, confidence=0.6) + _many("failed", 1, confidence=0.99)
    honest = _many("completed", 20, confidence=0.95)
    p = a.fleet_posture([_wf("liar", "Payments", liar), _wf("ok", "Invoices", honest)])
    names = [c["name"] for c in p["confident_liars"]]
    assert "Payments" in names and "Invoices" not in names


def test_fleet_verified_success_is_run_weighted():
    fleet = [
        _wf("a", "big", _many("completed", 90, confidence=0.9) + _many("failed", 10)),  # 90%
        _wf("b", "small", _many("failed", 10)),  # 0%
    ]
    p = a.fleet_posture(fleet)
    # 90 completed of 110 total runs -> ~0.818, run-weighted (not workflow-averaged).
    assert abs(p["fleet_verified_success_rate"] - 0.818) < 0.01
    assert p["total_runs"] == 110


def test_fleet_posture_orders_worst_first():
    fleet = [
        _wf("ready", "Ready wf", _many("completed", 22, confidence=0.95)),
        _wf("loop", "Loop wf", _many("failed", 8, failure_type="loading")),
    ]
    order = [c["tier"] for c in a.fleet_posture(fleet)["workflows"]]
    assert order[0] == a.IN_THE_LOOP and order[-1] == a.READY


def test_empty_fleet_is_honest():
    p = a.fleet_posture([])
    assert p["total_workflows"] == 0 and p["fleet_verified_success_rate"] is None
    assert p["confident_liars"] == []
