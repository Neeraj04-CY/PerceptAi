"""Chapter IX Step 1 — session truth end to end: the runner never claims work
it cannot execute, never opens a session against a dead desktop, and a run the
environment kills says so in the operator's words. Plus the plane-side status
composition (liveness + readiness) and its defence-in-depth claim gate.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api"))

import runners as svc  # noqa: E402
from runner import readiness as rd  # noqa: E402
from runner.config import RunnerConfig  # noqa: E402
from runner.worker import Worker  # noqa: E402
from perceptai.signing import derive_runner_key, sign_work_order  # noqa: E402

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
KEY = derive_runner_key("server-secret", "runner-1")


class FakePlane:
    def __init__(self, orders=None):
        self.orders = list(orders or [])
        self.results: list[dict] = []
        self.heartbeats: list[tuple] = []
        self.claims = 0

    def heartbeat(self, sid, readiness=None):
        self.heartbeats.append((sid, readiness))

    def claim(self):
        self.claims += 1
        return self.orders.pop(0) if self.orders else None

    def post_events(self, sid, events): pass
    def post_result(self, sid, report): self.results.append(report)
    def get_control(self, sid): return {"state": "running"}
    def post_approval_request(self, sid, request): pass
    def fetch_secret(self, sid, name): return None


def _config() -> RunnerConfig:
    return RunnerConfig(plane_url="http://x/api/v1", token="rk_t", signing_key=KEY,
                        readiness_recheck_s=0.01, readiness_probe_interval_s=0.0)


def _signed(instruction="open notepad", session_id="sess-1") -> dict:
    order = {"session_id": session_id, "instruction": instruction, "mode": "task"}
    return {"work_order": order, "signature": sign_work_order(KEY, order)}


def _worker(plane, readiness_state, session_factory=None) -> Worker:
    return Worker(plane, _config(), session_factory=session_factory or (lambda i: None),
                  readiness_probe=lambda: readiness_state)


# ------------------------------------------------------- refuse to open a run

def test_claimed_order_is_refused_when_the_desktop_died_before_the_first_action():
    """The desktop can lock between the claim and the first click. Report the
    environment honestly; never open a session against it."""
    plane = FakePlane()
    opened = []
    worker = _worker(plane, rd.Readiness(rd.LOCKED, "workstation locked", "unlock it"),
                     session_factory=lambda i: opened.append(i))
    report = worker.execute_work_order(_signed())

    assert report["status"] == "failed"
    assert "locked" in report["error"]
    assert report["readiness"]["state"] == rd.LOCKED
    assert opened == []                       # no AgentSession was ever constructed
    assert plane.results == [report]          # and the plane was told, honestly


def _sim_factory(tmp_path):
    """The ONE sanctioned test substrate: the real runtime over scripted screens."""
    from perceptai.contracts import ActionType, Step
    from perceptai.simulation import build_simulated_session

    plan = [[Step(action=ActionType.OPEN_APP, description="open notepad",
                  params={"app": "notepad", "wait": 0.0})]]

    def factory(instruction):
        session, _fakes, _events = build_simulated_session(plans=plan, workspace=tmp_path)
        return session
    return factory


def test_a_ready_host_executes_normally(tmp_path):
    plane = FakePlane()
    worker = _worker(plane, rd.Readiness(rd.READY, "ok"), session_factory=_sim_factory(tmp_path))
    report = worker.execute_work_order(_signed())
    assert report["status"] in ("completed", "unverified")
    assert "readiness" not in report          # nothing to explain on a healthy run


def test_a_desktop_lost_mid_run_stops_the_engine_and_says_why(tmp_path):
    """The whole point: no blind clicking at a lock screen, and the 7am operator
    reads a cause, not '0 steps, unverified'."""
    plane = FakePlane()
    states = [rd.Readiness(rd.READY, "ok")]

    def probe():
        return states.pop(0) if states else rd.Readiness(rd.LOCKED, "workstation locked")

    worker = Worker(plane, _config(), session_factory=_sim_factory(tmp_path),
                    readiness_probe=probe)
    report = worker.execute_work_order(_signed())

    assert report["status"] == "failed"
    assert report["readiness"]["state"] == rd.LOCKED
    assert "became unavailable mid-run" in report["error"]
    assert "workstation locked" in report["error"]


def test_bad_signature_is_still_rejected_before_readiness_is_even_consulted():
    plane = FakePlane()
    probed = []

    def probe():
        probed.append(1)
        return rd.Readiness(rd.READY, "ok")

    worker = Worker(plane, _config(), session_factory=lambda i: None, readiness_probe=probe)
    report = worker.execute_work_order({"work_order": {"session_id": "s"}, "signature": "bad"})
    assert "signature" in report["error"]
    assert probed == []                       # authenticity first, environment second


# ----------------------------------------------------------------- claim gate

def test_unready_runner_never_claims_and_still_heartbeats_its_reason():
    """The queue must hold the work for a healthy runner rather than burn an
    attempt against a lock screen — and the fleet must see WHY."""
    plane = FakePlane(orders=[_signed()])
    worker = _worker(plane, rd.Readiness(rd.LOCKED, "workstation locked"))

    import threading
    t = threading.Thread(target=worker.run_forever, daemon=True)
    t.start()
    import time
    time.sleep(0.08)
    worker.stop()
    t.join(timeout=2)

    assert plane.claims == 0                  # never asked for work
    assert plane.orders                       # the order is still queued
    states = [hb[1]["state"] for hb in plane.heartbeats if hb[1]]
    assert states and all(s == rd.LOCKED for s in states)


def test_worker_readiness_never_raises():
    def boom():
        raise RuntimeError("probe died")
    worker = Worker(FakePlane(), _config(), session_factory=lambda i: None,
                    readiness_probe=boom)
    assert worker.readiness().state == rd.UNKNOWN


# ---------------------------------------------------- plane-side status truth

def _hb(seconds_ago: float = 1.0) -> str:
    from datetime import timedelta
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def test_locked_runner_is_neither_online_nor_offline():
    """It is right there, healthy, heartbeating — and it cannot take work.
    Calling that 'online' is the lie session truth exists to prevent."""
    locked = {"state": rd.LOCKED, "can_execute": False}
    assert svc.derive_status(_hb(), None, NOW, locked) == "locked"
    assert svc.derive_status(_hb(), None, NOW, {"state": rd.READY, "can_execute": True}) == "online"
    assert svc.derive_status(None, None, NOW, locked) == "offline"      # no heartbeat wins
    assert svc.derive_status(_hb(9999), None, NOW, locked) == "offline"  # stale wins


def test_a_claim_outranks_readiness_because_it_is_actually_executing():
    stale_locked = {"state": rd.LOCKED, "can_execute": False}
    assert svc.derive_status(_hb(), "sess-1", NOW, stale_locked) == "busy"


def test_is_available_is_the_one_definition_of_can_take_work():
    assert svc.is_available("online") and svc.is_available("busy")
    for state in ("offline", rd.LOCKED, rd.LOGGED_OUT, rd.PERMISSION_DENIED,
                  rd.SCREEN_UNAVAILABLE, rd.UNKNOWN):
        assert not svc.is_available(state)


def test_public_runner_exposes_readiness_and_never_key_material():
    row = {"id": "r1", "name": "finance-vm", "token_hash": "SECRET", "token_prefix": "rk_a",
           "last_heartbeat_at": _hb(), "current_session_id": None,
           "readiness": {"state": rd.LOCKED, "detail": "workstation locked",
                         "can_execute": False}}
    pub = svc.public_runner(row, NOW)
    assert pub["status"] == "locked"
    assert pub["readiness"]["detail"] == "workstation locked"
    assert "token_hash" not in pub and "public_key" not in pub


def test_dispatch_warning_names_the_real_state_not_just_offline():
    from dispatch import dispatch_decision
    fleet = [{"id": "r-1", "name": "finance-vm", "status": "locked"}]
    d = dispatch_decision({"kind": "runner", "runner_id": "r-1"}, allow_local=False, runners=fleet)
    assert d["action"] == "enqueue"
    assert "locked" in d["warning"]   # actionable: the human knows to unlock it
    d = dispatch_decision({"kind": "any_available"}, allow_local=False, runners=fleet)
    assert "no runner is available" in d["warning"]
