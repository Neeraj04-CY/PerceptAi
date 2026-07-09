"""Sprint 8 Step 1 — the ONE dispatch path and the dispatcher-only scheduler.

Pure decisions (schedule_target, dispatch_decision) plus dispatch_workflow_run
and run_due_workflows against the in-memory Supabase fake. No screen, no
network, no real executor — the this_machine execution branch reuses the
pre-existing local executor verbatim and is exercised by the API's own paths.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))
sys.path.append(str(Path(__file__).parent))

from supafake import FakeSupabase  # noqa: E402
import dispatch as disp  # noqa: E402
import scheduler as sched  # noqa: E402

NOW = datetime(2026, 7, 9, 9, 0, tzinfo=timezone.utc)


def _workflow(**over):
    base = {
        "id": "wf-1", "org_id": "org-1", "workspace_id": "ws-1",
        "name": "Daily invoices", "instruction": "Open the ERP and export today's invoices",
        "variables": [], "mode": "task", "status": "published",
        "created_by": "user-1",
        "schedule": {"enabled": True, "interval_minutes": 60,
                     "target": {"kind": "any_available"}},
    }
    base.update(over)
    return base


def _online_runner(rid="run-1", **over):
    row = {"id": rid, "org_id": "org-1", "name": "finance-vm",
           "token_hash": "x", "token_prefix": "rk_x", "capabilities": {},
           "current_session_id": None,
           "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
           "created_at": NOW.isoformat()}
    row.update(over)
    return row


# ------------------------------------------------------------ pure decisions

def test_schedule_target_defaults_to_this_machine():
    assert disp.schedule_target({"schedule": {}}) == {"kind": "this_machine"}
    assert disp.schedule_target({}) == {"kind": "this_machine"}          # no schedule at all
    assert disp.schedule_target({"schedule": {"target": {"kind": "??"}}}) == {"kind": "this_machine"}


def test_schedule_target_normalizes_runner_and_any():
    wf = {"schedule": {"target": {"kind": "runner", "runner_id": "r-9"}}}
    assert disp.schedule_target(wf) == {"kind": "runner", "runner_id": "r-9"}
    # a runner pin without an id is meaningless -> safe default
    assert disp.schedule_target({"schedule": {"target": {"kind": "runner"}}}) == {"kind": "this_machine"}
    assert disp.schedule_target({"schedule": {"target": {"kind": "any_available"}}}) == {"kind": "any_available"}


def test_this_machine_blocked_unless_host_opted_in():
    blocked = disp.dispatch_decision({"kind": "this_machine"}, allow_local=False, runners=[])
    assert blocked["action"] == "blocked" and "ENABLE_SCHEDULER" in blocked["reason"]
    allowed = disp.dispatch_decision({"kind": "this_machine"}, allow_local=True, runners=[])
    assert allowed["action"] == "run_local"


def test_pinned_runner_dispatch():
    fleet = [{"id": "r-1", "name": "finance-vm", "status": "online"}]
    d = disp.dispatch_decision({"kind": "runner", "runner_id": "r-1"}, allow_local=False, runners=fleet)
    assert d == {"action": "enqueue", "target_runner_id": "r-1"}
    # offline pin still queues (the runner claims when it returns) but warns
    fleet[0]["status"] = "offline"
    d = disp.dispatch_decision({"kind": "runner", "runner_id": "r-1"}, allow_local=False, runners=fleet)
    assert d["action"] == "enqueue" and "offline" in d["warning"]
    # a pin to a deleted runner cannot be honored
    d = disp.dispatch_decision({"kind": "runner", "runner_id": "gone"}, allow_local=False, runners=fleet)
    assert d["action"] == "blocked"


def test_any_available_warns_on_empty_fleet():
    d = disp.dispatch_decision({"kind": "any_available"}, allow_local=False,
                               runners=[{"id": "r", "status": "online"}])
    assert d == {"action": "enqueue", "target_runner_id": None}
    d = disp.dispatch_decision({"kind": "any_available"}, allow_local=False,
                               runners=[{"id": "r", "status": "offline"}])
    assert d["action"] == "enqueue" and "no runner is online" in d["warning"]


# --------------------------------------------------------- dispatch (fake DB)

def test_dispatch_enqueues_into_the_one_queue():
    db = FakeSupabase()
    db.rows["runners"].append(_online_runner())
    result = disp.dispatch_workflow_run(db, _workflow(), allow_local=False)
    assert result["dispatched"] is True
    (session,) = db.rows["sessions"]
    assert session["status"] == "queued"           # the Sprint 4 queue, nothing new
    assert session["origin"] == "schedule"
    assert session["workflow_id"] == "wf-1"
    assert "target_runner_id" not in session       # any_available -> unpinned
    assert any(a["action"] == "schedule.dispatched" for a in db.rows["audit_log"])
    assert db.rows["attention_items"] == []        # healthy dispatch is silent


def test_dispatch_pins_target_runner():
    db = FakeSupabase()
    db.rows["runners"].append(_online_runner("r-7"))
    wf = _workflow(schedule={"enabled": True, "interval_minutes": 60,
                             "target": {"kind": "runner", "runner_id": "r-7"}})
    disp.dispatch_workflow_run(db, wf, allow_local=False)
    assert db.rows["sessions"][0]["target_runner_id"] == "r-7"


def test_dispatch_with_no_online_runner_queues_and_raises_attention():
    db = FakeSupabase()  # empty fleet
    result = disp.dispatch_workflow_run(db, _workflow(), allow_local=False)
    assert result["dispatched"] is True            # the queue holds it honestly
    assert db.rows["sessions"][0]["status"] == "queued"
    (item,) = db.rows["attention_items"]
    assert item["kind"] == "no_runner" and item["workflow_id"] == "wf-1"


def test_dispatch_blocked_this_machine_raises_attention_not_a_session():
    db = FakeSupabase()
    wf = _workflow(schedule={"enabled": True, "interval_minutes": 60})  # no target -> this_machine
    result = disp.dispatch_workflow_run(db, wf, allow_local=False)
    assert result["dispatched"] is False and result["action"] == "blocked"
    assert db.rows["sessions"] == []
    (item,) = db.rows["attention_items"]
    assert item["kind"] == "schedule_blocked"
    assert any(a["action"] == "schedule.blocked" for a in db.rows["audit_log"])


def test_dispatch_blocked_on_missing_required_variable():
    db = FakeSupabase()
    wf = _workflow(instruction="Email the report to {{recipient}}",
                   variables=[{"name": "recipient", "required": True}])
    result = disp.dispatch_workflow_run(db, wf, allow_local=False)
    assert result["dispatched"] is False
    assert "recipient" in result["reason"]
    assert db.rows["attention_items"][0]["kind"] == "schedule_blocked"


def test_dispatch_carries_retry_lineage():
    db = FakeSupabase()
    db.rows["runners"].append(_online_runner())
    disp.dispatch_workflow_run(db, _workflow(), allow_local=False,
                               retry_of="sess-dead", retry_count=2)
    session = db.rows["sessions"][0]
    assert session["retry_of"] == "sess-dead" and session["retry_count"] == 2


# ------------------------------------------------------- scheduler (dispatcher)

def _due_workflow(**over):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    wf = _workflow(schedule={"enabled": True, "interval_minutes": 60,
                             "next_run_at": past,
                             "target": {"kind": "any_available"}})
    wf.update(over)
    return wf


def test_scheduler_dispatches_due_and_bumps_next_run(monkeypatch):
    db = FakeSupabase()
    db.rows["workflows"].append(_due_workflow())
    calls = []
    monkeypatch.setattr(sched, "get_service_db", lambda: db)
    monkeypatch.setattr(sched, "dispatch_workflow_run",
                        lambda *a, **k: calls.append((a, k)) or {"dispatched": True})
    assert sched.run_due_workflows() == 1
    assert len(calls) == 1
    schedule = db.rows["workflows"][0]["schedule"]
    assert schedule["next_run_at"] > datetime.now(timezone.utc).isoformat()  # claimed ahead
    assert schedule["last_run_at"]


def test_scheduler_skips_disabled_not_due_and_missions(monkeypatch):
    db = FakeSupabase()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    db.rows["workflows"] += [
        _due_workflow(id="wf-a", schedule={"enabled": False, "interval_minutes": 60}),
        _due_workflow(id="wf-b", schedule={"enabled": True, "interval_minutes": 60,
                                           "next_run_at": future}),
        _due_workflow(id="wf-c", mode="mission"),
        {**_due_workflow(id="wf-d"), "schedule": None},   # never scheduled
    ]
    calls = []
    monkeypatch.setattr(sched, "get_service_db", lambda: db)
    monkeypatch.setattr(sched, "dispatch_workflow_run",
                        lambda *a, **k: calls.append(1) or {"dispatched": True})
    assert sched.run_due_workflows() == 0
    assert calls == []
    # the mission workflow was honestly audited as skipped, not silently dropped
    assert any(a["action"] == "schedule.skipped" for a in db.rows["audit_log"])


def test_scheduler_never_executes_itself():
    """The dispatcher-only invariant: scheduler.py must not import or touch
    the executor — execution happens in a runner or via dispatch's explicit
    this_machine branch."""
    import inspect
    source = inspect.getsource(sched)
    assert "execute_task_stream" not in source
    assert "from executor" not in source and "import executor" not in source
