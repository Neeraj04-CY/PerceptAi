"""Sprint 4 Step 2 — the thin runner against a fake transport and the REAL
runtime (simulation fakes). No network, no screen: proves the runner verifies
signed work, executes through one AgentSession, forwards canonical wire-v1
events, and reports the result — without the engine knowing about transport."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from perceptai.contracts import ActionType, Step  # noqa: E402
from perceptai.simulation import build_simulated_session  # noqa: E402
from runner.config import RunnerConfig  # noqa: E402
from runner.worker import Worker  # noqa: E402
from runner_signing import sign_work_order  # noqa: E402

KEY = "test-signing-key"


def _plan():
    return [[
        Step(action=ActionType.OPEN_APP, description="open notepad",
             params={"app": "notepad", "wait": 0.0}),
        Step(action=ActionType.TYPE, description="type hello",
             params={"text": "hello world", "app": "notepad"}),
    ]]


def _session_factory(tmp_path):
    def factory(instruction):
        session, _fakes, _events = build_simulated_session(plans=_plan(), workspace=tmp_path)
        return session
    return factory


def _ready():
    """Session truth is an injected seam precisely so unit tests never depend on
    the host's real desktop (a headless CI box is not 'ready')."""
    from runner.readiness import READY, Readiness
    return Readiness(state=READY, detail="simulated host")


def _signed(instruction="open notepad and type hello world", session_id="sess-1"):
    order = {"session_id": session_id, "instruction": instruction, "mode": "task",
             "org_id": "o", "workspace_id": None, "approval_risk_threshold": "",
             "issued_at": "2026-07-06T12:00:00+00:00",
             "expires_at": "2026-07-06T12:05:00+00:00", "nonce": "abcd1234"}
    return {"work_order": order, "signature": sign_work_order(KEY, order)}


class FakePlane:
    """Records everything the worker sends; serves one work order then dries up."""
    def __init__(self, order=None):
        self._order = order
        self._served = False
        self.heartbeats: list = []
        self.events: list[dict] = []
        self.result = None

    def heartbeat(self, current_session_id, readiness=None):
        self.heartbeats.append(current_session_id)

    def claim(self):
        if self._served or self._order is None:
            return None
        self._served = True
        return self._order

    def post_events(self, session_id, events):
        self.events.extend(events)

    def post_result(self, session_id, report):
        self.result = (session_id, report)


def _cfg():
    return RunnerConfig(plane_url="http://x", token="rk_x", signing_key=KEY,
                        event_flush_interval_s=0.02, heartbeat_interval_s=0.05)


# ------------------------------------------------------------- execution

def test_executes_signed_order_and_reports_result(tmp_path):
    plane = FakePlane()
    worker = Worker(plane, _cfg(), session_factory=_session_factory(tmp_path),
                    readiness_probe=_ready)
    report = worker.execute_work_order(_signed())

    assert report["status"] == "completed"
    assert plane.result is not None
    sid, sent = plane.result
    assert sid == "sess-1" and sent["status"] == "completed"
    assert sent["steps"], "steps should be reported for the dashboard"


def test_forwards_canonical_wire_v1_events(tmp_path):
    plane = FakePlane()
    worker = Worker(plane, _cfg(), session_factory=_session_factory(tmp_path),
                    readiness_probe=_ready)
    worker.execute_work_order(_signed())

    assert plane.events, "events must be forwarded to the plane"
    # wire v1 shape: {type, seq, task_id, timestamp, data}
    e = plane.events[0]
    assert {"type", "seq", "task_id", "timestamp", "data"} <= set(e)
    types = [e["type"] for e in plane.events]
    assert "task_started" in types and "task_completed" in types
    # seqs are strictly increasing (ordered stream)
    seqs = [e["seq"] for e in plane.events]
    assert seqs == sorted(seqs)


def test_rejects_tampered_order_without_executing(tmp_path):
    plane = FakePlane()
    worker = Worker(plane, _cfg(), session_factory=_session_factory(tmp_path),
                    readiness_probe=_ready)
    signed = _signed()
    signed["work_order"]["instruction"] = "delete everything"  # tamper after signing

    report = worker.execute_work_order(signed)
    assert report["status"] == "failed"
    assert "signature" in (report["error"] or "")
    assert plane.events == []            # never executed
    assert plane.result is not None       # but the failure was reported honestly


# --------------------------------------------------------- claim/heartbeat loop

def test_run_forever_claims_executes_and_heartbeats(tmp_path):
    plane = FakePlane(_signed())
    worker = Worker(plane, _cfg(), session_factory=_session_factory(tmp_path),
                    readiness_probe=_ready)
    t = threading.Thread(target=worker.run_forever, daemon=True)
    t.start()

    deadline = time.time() + 5
    while plane.result is None and time.time() < deadline:
        time.sleep(0.02)
    worker.stop()
    t.join(timeout=3)

    assert plane.result is not None and plane.result[1]["status"] == "completed"
    assert plane.heartbeats, "the heartbeat loop should have pinged the plane"


def test_event_pump_re_enqueues_on_send_failure():
    """Graceful disconnect: a failed send must not lose events — they are
    re-queued and retried (the plane's ingest dedups on seq)."""
    from perceptai.events import EventBus
    from runner.worker import EventPump

    delivered: list[dict] = []
    state = {"fail": True}

    def send(batch):
        if state["fail"]:
            return False          # transport down
        delivered.extend(batch)
        return True

    pump = EventPump(EventBus(), send, flush_interval_s=0.02, batch_max=10)
    pump._q.put({"seq": 1, "type": "log"})

    pump._flush(pump._drain(0))   # send fails
    assert pump._q.qsize() == 1   # nothing lost — event is back in the queue
    assert delivered == []

    state["fail"] = True and False  # transport recovers
    pump._flush(pump._drain(0))
    assert delivered and delivered[0]["seq"] == 1
    assert pump._q.qsize() == 0
