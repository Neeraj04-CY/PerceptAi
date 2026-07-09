"""Sprint 8 Step 3 — failure policy: bounded opt-in retries for honest FAILED
results of unattended runs; everything a human must see reaches Attention.
Kept strictly separate from reclaim semantics (tests/test_runners.py pins
those): dead-letters are never policy-retried.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))
sys.path.append(str(Path(__file__).parent))

from supafake import FakeSupabase  # noqa: E402
import dispatch as disp  # noqa: E402
import failure_policy as fp  # noqa: E402
import runners as runner_svc  # noqa: E402


def _workflow(retries=2, notify=True):
    return {
        "id": "wf-1", "org_id": "org-1", "workspace_id": "ws-1",
        "name": "Daily invoices", "instruction": "Export today's invoices",
        "variables": [], "mode": "task", "status": "published",
        "created_by": "user-1",
        "schedule": {"enabled": True, "interval_minutes": 60,
                     "target": {"kind": "any_available"},
                     "on_failure": {"retries": retries, "notify": notify}},
    }


def _failed_session(**over):
    base = {"id": "sess-1", "org_id": "org-1", "workspace_id": "ws-1",
            "workflow_id": "wf-1", "origin": "schedule", "retry_count": 0,
            "status": "failed", "error": "window never appeared"}
    base.update(over)
    return base


# ------------------------------------------------------------ pure decisions

def test_policy_defaults_are_safe():
    assert fp.failure_policy(None) == {"retries": 0, "notify": True}
    assert fp.failure_policy({"schedule": {}}) == {"retries": 0, "notify": True}
    assert fp.failure_policy({"schedule": {"on_failure": {"retries": "junk"}}}) == \
        {"retries": 0, "notify": True}


def test_policy_retries_are_hard_capped():
    wf = {"schedule": {"on_failure": {"retries": 99}}}
    assert fp.failure_policy(wf)["retries"] == fp.MAX_POLICY_RETRIES
    assert fp.failure_policy({"schedule": {"on_failure": {"retries": -5}}})["retries"] == 0


def test_retry_decision_only_for_unattended_runs():
    policy = {"retries": 2, "notify": True}
    d = fp.retry_decision({"origin": "user", "retry_count": 0}, policy)
    assert d["retry"] is False           # an operator was watching — their call
    d = fp.retry_decision({"origin": "schedule", "retry_count": 0}, policy)
    assert d == {"retry": True, "next_retry_count": 1}


def test_retry_decision_respects_the_bound():
    policy = {"retries": 2, "notify": True}
    assert fp.retry_decision({"origin": "schedule", "retry_count": 1}, policy)["retry"] is True
    assert fp.retry_decision({"origin": "schedule", "retry_count": 2}, policy)["retry"] is False
    assert fp.retry_decision({"origin": "schedule", "retry_count": 0},
                             {"retries": 0, "notify": True})["retry"] is False


# --------------------------------------------------------------- apply (fake DB)

def test_failed_run_with_retries_left_is_redispatched(monkeypatch):
    db = FakeSupabase()
    db.rows["workflows"].append(_workflow(retries=2))
    dispatched = []
    monkeypatch.setattr(disp, "dispatch_workflow_run",
                        lambda *a, **k: dispatched.append(k) or
                        {"dispatched": True, "session_id": "sess-2"})
    outcome = fp.apply_failure_policy(db, _failed_session())
    assert outcome["retry"] is True and outcome["retry_session_id"] == "sess-2"
    assert dispatched[0]["retry_of"] == "sess-1"
    assert dispatched[0]["retry_count"] == 1
    assert any(a["action"] == "schedule.retried" for a in db.rows["audit_log"])
    assert db.rows["attention_items"] == []   # a silent retry is the point


def test_exhausted_retries_reach_attention():
    db = FakeSupabase()
    db.rows["workflows"].append(_workflow(retries=1))
    outcome = fp.apply_failure_policy(db, _failed_session(retry_count=1))
    assert outcome == {"retry": False, "notified": True}
    (item,) = db.rows["attention_items"]
    assert item["kind"] == "run_failed"
    assert item["session_id"] == "sess-1"
    assert item["detail"]["retries_used"] == 1


def test_notify_false_stays_silent():
    db = FakeSupabase()
    db.rows["workflows"].append(_workflow(retries=0, notify=False))
    outcome = fp.apply_failure_policy(db, _failed_session())
    assert outcome == {"retry": False, "notified": False}
    assert db.rows["attention_items"] == []


def test_interactive_failures_are_not_policy_handled():
    db = FakeSupabase()
    db.rows["workflows"].append(_workflow(retries=3))
    outcome = fp.apply_failure_policy(db, _failed_session(origin="user"))
    assert outcome == {"retry": False, "notified": False}
    assert db.rows["sessions"] == [] and db.rows["attention_items"] == []


# ------------------------------------------- reclaim stays separate (invariant)

def test_dead_letter_reaches_attention_but_is_never_policy_retried(monkeypatch):
    """A runner died mid-execution: reclaim dead-letters (Sprint 5 invariant),
    the operator is told, and NO retry happens even with retries declared —
    progress was unknown and a real-screen task is not idempotent."""
    db = FakeSupabase()
    db.rows["workflows"].append(_workflow(retries=3))
    db.rows["sessions"].append({
        "id": "sess-9", "org_id": "org-1", "workspace_id": "ws-1",
        "workflow_id": "wf-1", "origin": "schedule", "status": "running",
        "attempts": 1, "claim_expires_at": "2000-01-01T00:00:00+00:00",
        "instruction": "Export today's invoices"})
    retried = []
    monkeypatch.setattr(disp, "dispatch_workflow_run",
                        lambda *a, **k: retried.append(1) or {"dispatched": True})
    assert runner_svc.reclaim_stale(db, max_attempts=3) == 1
    session = db.rows["sessions"][0]
    assert session["status"] == "failed" and "duplicate" in session["error"]
    (item,) = db.rows["attention_items"]
    assert item["kind"] == "dead_letter" and item["session_id"] == "sess-9"
    assert retried == []                      # policy never touches uncertain state
