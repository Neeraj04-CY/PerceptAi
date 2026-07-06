"""Trust layer (Sprint 3): control checkpoint, risk observation, and the
risk-gated approval flow. Fully faked — no LLM, no screen. Also unit-tests
the ThreadedControlChannel state machine directly."""
from __future__ import annotations

import threading
import time

from perceptai.contracts import (
    ActionType,
    ApprovalDecision,
    ApprovalResolution,
    RunControl,
    Step,
)
from perceptai.control import ControlChannel, ThreadedControlChannel
from perceptai.events import EventType
from perceptai.simulation import fast_config


def _step(action, description="", **params):
    return Step(action=ActionType(action), description=description, params=params)


class ScriptedControl(ControlChannel):
    """Deterministic control for tests: a scripted state sequence and a fixed
    approval resolution. No threads, no timing."""

    def __init__(self, states=None, approval=None):
        self._states = list(states or [])
        self._approval = approval
        self.approval_requests: list = []

    def state(self):
        return self._states.pop(0) if self._states else RunControl.RUNNING

    def wait_for_change(self, timeout_s):
        return RunControl.RUNNING  # a paused run always resumes in tests

    def request_approval(self, request, timeout_s):
        self.approval_requests.append(request)
        return self._approval or ApprovalResolution(
            decision=ApprovalDecision.GRANT, auto=True)


def _types(events):
    return [e.type for e in events]


# ------------------------------------------------------------ control checkpoint

def test_default_channel_is_pure_passthrough(harness):
    """No controller attached => not one trust-control event, run unchanged."""
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0),
                _step("type", "type notes", text="meeting notes", app="notepad")]],
    )
    result = session.run("take notes")
    assert fakes["apps"].opened == ["notepad"]
    kinds = _types(events)
    assert EventType.EXECUTION_PAUSED not in kinds
    assert EventType.EXECUTION_STOPPED not in kinds
    assert EventType.APPROVAL_REQUESTED not in kinds


def test_stop_halts_before_any_action(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.control = ScriptedControl(states=[RunControl.STOPPING])
    result = session.run("open notepad")
    assert fakes["apps"].opened == []           # stopped before acting
    assert result.status.value == "failed"
    assert result.failure_type == "stopped"
    assert "Execution stopped by user" in result.errors
    assert EventType.EXECUTION_STOPPED in _types(events)


def test_pause_then_resume_completes(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.control = ScriptedControl(states=[RunControl.PAUSED])
    result = session.run("open notepad")
    assert fakes["apps"].opened == ["notepad"]  # paused, then ran to completion
    kinds = _types(events)
    assert EventType.EXECUTION_PAUSED in kinds
    assert EventType.EXECUTION_RESUMED in kinds
    # paused strictly before resumed
    assert kinds.index(EventType.EXECUTION_PAUSED) < kinds.index(EventType.EXECUTION_RESUMED)


# ------------------------------------------------------------ risk observation

def test_risk_observed_but_not_gated_by_default(harness):
    """A destructive action is flagged for the cockpit, but with no approval
    threshold it still executes — risk is observed, not gated."""
    session, fakes, events = harness(
        plans=[[_step("open_app", "open files", app="files", wait=0.0),
                _step("click", "click the Delete button", find="Delete")]],
        screens=[["Delete", "Rename", "Trash"]],
    )
    result = session.run("delete the file")
    risk_events = [e for e in events if e.type == EventType.RISK_FLAGGED]
    assert risk_events, "a destructive click must be flagged"
    assert risk_events[0].payload["level"] == "high"
    assert any(r["kind"] == "irreversible" for r in risk_events[0].payload["risks"])
    # not gated: no approval was requested and the click actually dispatched
    assert EventType.APPROVAL_REQUESTED not in _types(events)
    assert fakes["actions"].clicks, "the click should have executed"


def test_benign_action_is_not_flagged(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open files", app="files", wait=0.0),
                _step("click", "click the Rename button", find="Rename")]],
        screens=[["Delete", "Rename", "Trash"]],
    )
    session.run("rename the file")
    assert EventType.RISK_FLAGGED not in _types(events)


# ------------------------------------------------------------ approval gating

def test_approval_required_and_granted(harness):
    cfg = fast_config(approval_risk_threshold="medium")
    session, fakes, events = harness(
        plans=[[_step("open_app", "open files", app="files", wait=0.0),
                _step("click", "click the Delete button", find="Delete")]],
        screens=[["Delete", "Rename", "Trash"]],
        config=cfg,
    )
    session.control = ScriptedControl(
        approval=ApprovalResolution(decision=ApprovalDecision.GRANT, decided_by="op"))
    session.run("delete the file")
    kinds = _types(events)
    assert EventType.APPROVAL_REQUESTED in kinds
    decided = [e for e in events if e.type == EventType.APPROVAL_DECIDED]
    assert decided and decided[0].payload["decision"] == "grant"
    assert fakes["actions"].clicks, "granted action must execute"


def test_approval_required_and_denied_blocks_action(harness):
    cfg = fast_config(approval_risk_threshold="medium")
    session, fakes, events = harness(
        plans=[[_step("open_app", "open files", app="files", wait=0.0),
                _step("click", "click the Delete button", find="Delete")]],
        screens=[["Delete", "Rename", "Trash"]],
        config=cfg,
    )
    control = ScriptedControl(
        approval=ApprovalResolution(decision=ApprovalDecision.DENY, reason="not approved"))
    session.control = control
    session.run("delete the file")
    kinds = _types(events)
    assert EventType.APPROVAL_REQUESTED in kinds
    decided = [e for e in events if e.type == EventType.APPROVAL_DECIDED]
    assert decided and decided[0].payload["decision"] == "deny"
    assert fakes["actions"].clicks == [], "a denied action must never execute"
    assert control.approval_requests[0].action == "click"


def test_threshold_off_does_not_request_approval(harness):
    """Risk is high, but with gating off (default) no approval is requested."""
    session, fakes, events = harness(
        plans=[[_step("open_app", "open files", app="files", wait=0.0),
                _step("click", "click the Delete button", find="Delete")]],
        screens=[["Delete", "Rename", "Trash"]],
    )
    session.control = ScriptedControl(
        approval=ApprovalResolution(decision=ApprovalDecision.DENY))
    session.run("delete the file")
    assert EventType.APPROVAL_REQUESTED not in _types(events)
    assert fakes["actions"].clicks, "ungated high-risk action still executes"


# ------------------------------------------- ThreadedControlChannel state machine

def test_threaded_channel_pause_resume_stop():
    ch = ThreadedControlChannel()
    assert ch.state() == RunControl.RUNNING
    ch.pause()
    assert ch.state() == RunControl.PAUSED
    ch.resume()
    assert ch.state() == RunControl.RUNNING
    ch.stop()
    assert ch.state() == RunControl.STOPPING
    # stop is terminal: a later pause cannot revive a stopping run
    ch.pause()
    assert ch.state() == RunControl.STOPPING


def test_threaded_channel_wait_unblocks_on_resume():
    ch = ThreadedControlChannel()
    ch.pause()
    threading.Timer(0.05, ch.resume).start()
    t0 = time.time()
    state = ch.wait_for_change(2.0)
    assert state == RunControl.RUNNING
    assert time.time() - t0 < 1.5           # returned on resume, not on timeout


def test_threaded_channel_approval_roundtrip():
    ch = ThreadedControlChannel()
    from perceptai.contracts import ApprovalRequest

    req = ApprovalRequest(request_id="abc", step_index=1, action="click",
                          summary="click Delete")

    def approve():
        time.sleep(0.05)
        assert ch.pending_approval().request_id == "abc"
        ch.resolve_approval("abc", ApprovalDecision.GRANT, decided_by="op")

    threading.Thread(target=approve).start()
    res = ch.request_approval(req, timeout_s=2.0)
    assert res.decision == ApprovalDecision.GRANT
    assert res.decided_by == "op"
    assert ch.pending_approval() is None      # cleared after resolution


def test_threaded_channel_approval_times_out_to_deny():
    ch = ThreadedControlChannel()
    from perceptai.contracts import ApprovalRequest

    req = ApprovalRequest(request_id="t", step_index=1, action="click", summary="x")
    res = ch.request_approval(req, timeout_s=0.05)
    assert res.decision == ApprovalDecision.DENY
    assert res.auto is True
