"""Sprint 4 Step 4 — live relay fan-out and wire-v1 -> v0 translation, so a
remote runner's stream drives the same cockpit as a local run."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from perceptai.streaming import platform_to_legacy  # noqa: E402
from relay import Relay  # noqa: E402


# ------------------------------------------------------------ translation

def test_step_completed_v1_to_v0():
    v0 = platform_to_legacy("step_completed", {
        "step_number": 2, "description": "type hello", "action": "type",
        "status": "completed", "duration_s": 0.4, "data": {}}, task_id="t", seq=5)
    assert v0["type"] == "step_complete"
    assert v0["step"]["step_number"] == 2
    assert v0["step"]["status"] == "completed"


def test_trust_event_v1_to_v0():
    v0 = platform_to_legacy("risk_flagged", {
        "level": "high", "summary": "irreversible", "risks": []}, seq=7)
    assert v0["type"] == "trust" and v0["kind"] == "risk_flagged"
    assert v0["level"] == "high"


def test_task_completed_v1_to_v0():
    v0 = platform_to_legacy("task_completed", {"status": "completed",
                                               "duration_s": 12.0}, seq=9)
    assert v0["type"] == "complete" and v0["status"] == "completed"


def test_unknown_type_returns_none():
    assert platform_to_legacy("not_a_real_event", {}, seq=1) is None


# ------------------------------------------------------------------ relay

def test_relay_publishes_to_subscribers():
    r = Relay()
    q = r.subscribe("sess-1")
    r.publish("sess-1", [{"seq": 1, "type": "x"}, {"seq": 2, "type": "y"}])
    assert q.get_nowait()["seq"] == 1
    assert q.get_nowait()["seq"] == 2


def test_relay_isolates_sessions_and_unsubscribe():
    r = Relay()
    q1 = r.subscribe("a")
    q2 = r.subscribe("b")
    r.publish("a", [{"seq": 1}])
    assert q1.qsize() == 1 and q2.qsize() == 0     # session isolation
    r.unsubscribe("a", q1)
    r.publish("a", [{"seq": 2}])
    assert q1.qsize() == 1                          # no more delivery after unsubscribe


def test_relay_full_queue_drops_without_raising():
    r = Relay()
    q = r.subscribe("s")
    # fill beyond capacity — publish must never raise (viewer backfills from DB)
    r.publish("s", [{"seq": i} for i in range(5000)])
    assert q.qsize() <= 4000
