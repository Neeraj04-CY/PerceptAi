"""Sprint 4 Step 3 — RemoteControlChannel + durable control over the runner.

Proves the Sprint 3 ControlChannel abstraction works UNCHANGED across a
network: the runtime pauses/resumes/stops and gates on approval by reading the
plane's durable control record, and never learns transport is involved."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from perceptai.contracts import (  # noqa: E402
    ActionType,
    ApprovalDecision,
    ApprovalRequest,
    RunControl,
    Step,
)
from perceptai.simulation import build_simulated_session, fast_config  # noqa: E402
from runner.config import RunnerConfig  # noqa: E402
from runner.control import RemoteControlChannel  # noqa: E402
from runner.worker import Worker  # noqa: E402
from runner_signing import sign_work_order  # noqa: E402

KEY = "test-signing-key"


# ------------------------------------------------------- RemoteControlChannel

class FakeControlClient:
    def __init__(self, state="running", decision=None):
        self.state = state
        self.decision = decision
        self.requests: list = []
        self.raise_on_get = False

    def get_control(self, session_id):
        if self.raise_on_get:
            raise ConnectionError("plane unreachable")
        return {"state": self.state, "approval_decision": self.decision}

    def post_approval_request(self, session_id, request):
        self.requests.append(request)


def _chan(client):
    return RemoteControlChannel(client, "sess-1", poll_interval_s=0.01)


def test_state_maps_plane_strings():
    assert _chan(FakeControlClient("running")).state() == RunControl.RUNNING
    assert _chan(FakeControlClient("paused")).state() == RunControl.PAUSED
    assert _chan(FakeControlClient("stopping")).state() == RunControl.STOPPING


def test_state_fails_open_on_transport_error():
    c = FakeControlClient("paused")
    c.raise_on_get = True
    assert _chan(c).state() == RunControl.RUNNING  # never blocks a healthy run


def test_wait_for_change_returns_on_resume():
    c = FakeControlClient("paused")
    threading.Timer(0.05, lambda: setattr(c, "state", "running")).start()
    assert _chan(c).wait_for_change(2.0) == RunControl.RUNNING


def test_wait_for_change_times_out_still_paused():
    c = FakeControlClient("paused")
    assert _chan(c).wait_for_change(0.05) == RunControl.PAUSED


def test_request_approval_grant_and_deny():
    req = ApprovalRequest(request_id="rq1", step_index=1, action="click", summary="x")

    grant = FakeControlClient(decision={"request_id": "rq1", "decision": "grant",
                                        "decided_by": "op", "reason": ""})
    res = _chan(grant).request_approval(req, 1.0)
    assert res.decision == ApprovalDecision.GRANT and res.decided_by == "op"
    assert grant.requests, "the request is posted so a decision can match it"

    deny = FakeControlClient(decision={"request_id": "rq1", "decision": "deny"})
    assert _chan(deny).request_approval(req, 1.0).decision == ApprovalDecision.DENY


def test_request_approval_times_out_to_deny():
    req = ApprovalRequest(request_id="rq1", step_index=1, action="click", summary="x")
    res = _chan(FakeControlClient()).request_approval(req, 0.05)
    assert res.decision == ApprovalDecision.DENY and res.auto is True


# --------------------------------------------- worker honoring remote control

class ControlPlane:
    """Fake plane implementing execution + control transport, with a mutable
    control state a test can flip."""
    def __init__(self, order, state="running"):
        self._order = order
        self._served = False
        self.events: list[dict] = []
        self.result = None
        self.heartbeats: list = []
        self.state = state
        self.approval_decision = None
        self.approval_requests: list = []

    # execution transport
    def heartbeat(self, sid): self.heartbeats.append(sid)
    def claim(self):
        if self._served:
            return None
        self._served = True
        return self._order
    def post_events(self, sid, events): self.events.extend(events)
    def post_result(self, sid, report): self.result = (sid, report)
    # control transport
    def get_control(self, sid):
        return {"state": self.state, "approval_decision": self.approval_decision}
    def post_approval_request(self, sid, request):
        self.approval_requests.append(request)


def _signed(session_id="sess-1"):
    order = {"session_id": session_id, "instruction": "open notepad and type hi",
             "mode": "task", "approval_risk_threshold": "", "nonce": "n"}
    return {"work_order": order, "signature": sign_work_order(KEY, order)}


def _factory(tmp_path):
    plan = [[Step(action=ActionType.OPEN_APP, description="open notepad",
                  params={"app": "notepad", "wait": 0.0})]]
    def make(instruction):
        session, _f, _e = build_simulated_session(plans=plan, workspace=tmp_path)
        return session
    return make


def test_worker_honors_remote_pause_then_resume(tmp_path):
    plane = ControlPlane(_signed(), state="paused")
    threading.Timer(0.1, lambda: setattr(plane, "state", "running")).start()

    cfg = RunnerConfig(plane_url="x", token="rk", signing_key=KEY,
                       event_flush_interval_s=0.02)
    worker = Worker(plane, cfg, session_factory=_factory(tmp_path),
                    control_factory=lambda sid: RemoteControlChannel(plane, sid,
                                                                     poll_interval_s=0.02))
    report = worker.execute_work_order(_signed())

    assert report["status"] == "completed"  # paused, resumed, then finished
    types = [e["type"] for e in plane.events]
    assert "execution_paused" in types
    assert "execution_resumed" in types
    assert types.index("execution_paused") < types.index("execution_resumed")


def test_worker_honors_remote_stop(tmp_path):
    plane = ControlPlane(_signed(), state="stopping")
    cfg = RunnerConfig(plane_url="x", token="rk", signing_key=KEY,
                       event_flush_interval_s=0.02)
    worker = Worker(plane, cfg, session_factory=_factory(tmp_path),
                    control_factory=lambda sid: RemoteControlChannel(plane, sid,
                                                                     poll_interval_s=0.02))
    report = worker.execute_work_order(_signed())

    # stopped before acting -> failed with the honest 'stopped' cause
    assert report["status"] == "failed"
    assert report["result"]["failure_type"] == "stopped"
    assert "execution_stopped" in [e["type"] for e in plane.events]
