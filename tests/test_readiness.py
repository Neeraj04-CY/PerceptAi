"""Chapter IX Step 1 — Session Truth.

The platform must never pretend work can execute when the environment cannot.
`evaluate()` is pure, so every state (including ones that need a locked Windows
box to reproduce) is tested here deterministically. The guard and the claim gate
are tested against fakes: no screen, no network, no plane.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from perceptai.contracts import ApprovalRequest, RunControl  # noqa: E402
from runner import readiness as rd  # noqa: E402
from runner.control import ReadinessGuard  # noqa: E402


def _signals(**over) -> rd.DesktopSignals:
    base = dict(supported=True, console_session=1, process_session=1,
                input_desktop_open=True, screen_size=(1920, 1080))
    base.update(over)
    return rd.DesktopSignals(**base)


# ------------------------------------------------------------ every state

def test_ready_when_console_session_is_ours_and_unlocked():
    r = rd.evaluate(_signals())
    assert r.state == rd.READY and r.can_execute is True


def test_locked_workstation():
    r = rd.evaluate(_signals(input_desktop_open=False))
    assert r.state == rd.LOCKED and r.can_execute is False
    assert "locked" in r.detail and r.fix  # explains itself AND how to fix it


def test_logged_out_console():
    r = rd.evaluate(_signals(console_session=rd.NO_SESSION, input_desktop_open=False))
    # Root cause, not the symptom: a logged-out console has no input desktop
    # either, and reporting LOCKED would send the operator chasing the wrong fix.
    assert r.state == rd.LOGGED_OUT


def test_session_zero_service_is_permission_denied_not_locked():
    r = rd.evaluate(_signals(process_session=0, console_session=2, input_desktop_open=False))
    assert r.state == rd.PERMISSION_DENIED
    assert "session 0" in r.detail or "!=" in r.detail
    assert "console user" in r.fix   # the actual fix, not "unlock the machine"


def test_screen_unavailable_when_desktop_open_but_no_display():
    r = rd.evaluate(_signals(screen_size=None))
    assert r.state == rd.SCREEN_UNAVAILABLE


def test_network_unavailable_outranks_a_healthy_desktop():
    r = rd.evaluate(_signals(plane_reachable=False))
    assert r.state == rd.NETWORK_UNAVAILABLE and r.can_execute is False


def test_unknown_when_probes_cannot_determine_anything():
    r = rd.evaluate(rd.DesktopSignals(supported=True, input_desktop_open=None, screen_size=None))
    assert r.state == rd.UNKNOWN
    assert r.can_execute is False     # never execute on an unknown environment


def test_non_windows_falls_back_to_the_screen_signal_only():
    # Never claim LOCKED/LOGGED_OUT we cannot observe.
    assert rd.evaluate(rd.DesktopSignals(supported=False, screen_size=(1024, 768))).state == rd.READY
    assert rd.evaluate(rd.DesktopSignals(supported=False, screen_size=None)).state == rd.UNKNOWN


def test_only_ready_can_execute():
    for state in (rd.LOCKED, rd.LOGGED_OUT, rd.SCREEN_UNAVAILABLE,
                  rd.PERMISSION_DENIED, rd.NETWORK_UNAVAILABLE, rd.UNKNOWN):
        assert rd.Readiness(state, "x").can_execute is False
    assert rd.Readiness(rd.READY, "x").can_execute is True


def test_every_state_explains_itself():
    """No ambiguous failures: each state carries a human explanation, and every
    non-ready state carries the exact fix."""
    for state in (rd.READY, rd.LOCKED, rd.LOGGED_OUT, rd.SCREEN_UNAVAILABLE,
                  rd.PERMISSION_DENIED, rd.NETWORK_UNAVAILABLE, rd.UNKNOWN):
        detail, fix = rd._EXPLAIN[state]
        assert detail
        if state != rd.READY:
            assert fix, f"{state} must tell the operator how to fix it"


def test_explanations_are_ascii_for_windows_consoles():
    """`--doctor` prints these to cp1252 consoles; a typographic dash crashes it."""
    for detail, fix in rd._EXPLAIN.values():
        (detail + fix).encode("ascii")   # raises if any non-ASCII slipped in


def test_probe_never_raises_and_degrades_to_unknown():
    def boom():
        raise RuntimeError("no win32 here")
    assert rd.probe(boom).state == rd.UNKNOWN


def test_probe_overlays_plane_reachability():
    r = rd.probe(lambda: _signals(), plane_reachable=False)
    assert r.state == rd.NETWORK_UNAVAILABLE


# ----------------------------------------------------- mid-run readiness guard

class _Inner:
    """A control channel that is always happily running."""
    def __init__(self):
        self.approvals = 0

    def state(self):
        return RunControl.RUNNING

    def wait_for_change(self, timeout_s):
        return RunControl.RUNNING

    def request_approval(self, request, timeout_s):
        self.approvals += 1
        from perceptai.contracts import ApprovalDecision, ApprovalResolution
        return ApprovalResolution(decision=ApprovalDecision.GRANT)


def _request() -> ApprovalRequest:
    return ApprovalRequest(request_id="r1", step_index=0, action="click",
                           summary="click Pay")


def test_guard_is_transparent_while_the_desktop_is_healthy():
    inner = _Inner()
    guard = ReadinessGuard(inner, lambda: rd.Readiness(rd.READY, "ok"))
    assert guard.state() is RunControl.RUNNING
    assert guard.wait_for_change(0.01) is RunControl.RUNNING
    assert guard.lost_readiness is None


def test_guard_stops_the_run_when_the_desktop_is_lost():
    states = [rd.Readiness(rd.READY, "ok"), rd.Readiness(rd.LOCKED, "workstation locked")]
    guard = ReadinessGuard(_Inner(), lambda: states.pop(0) if states else rd.Readiness(rd.LOCKED, "x"),
                           min_interval_s=0.0)
    assert guard.state() is RunControl.RUNNING          # first checkpoint: healthy
    assert guard.state() is RunControl.STOPPING         # then the screen locks
    assert guard.lost_readiness.state == rd.LOCKED      # and we know why


def test_guard_latches_and_never_flaps_back_to_running():
    """A desktop that briefly reappears must not resume a run that was already
    stopping — the engine has already begun aborting."""
    seq = [rd.Readiness(rd.LOCKED, "x"), rd.Readiness(rd.READY, "ok")]
    guard = ReadinessGuard(_Inner(), lambda: seq.pop(0), min_interval_s=0.0)
    assert guard.state() is RunControl.STOPPING
    assert guard.state() is RunControl.STOPPING


def test_guard_throttles_the_probe_off_the_engine_hot_path():
    """The engine calls state() many times per cycle; the real probe touches
    Win32 and the display. Cache it, or every control checkpoint pays for it."""
    calls = []
    clock = [100.0]

    def probe():
        calls.append(1)
        return rd.Readiness(rd.READY, "ok")

    guard = ReadinessGuard(_Inner(), probe, min_interval_s=2.0, clock=lambda: clock[0])
    for _ in range(50):
        guard.state()
    assert len(calls) == 1              # 50 checkpoints, one probe

    clock[0] += 2.5                     # past the window
    guard.state()
    assert len(calls) == 2


def test_throttling_never_delays_a_lock_beyond_the_window():
    clock = [0.0]
    seq = [rd.Readiness(rd.READY, "ok"), rd.Readiness(rd.LOCKED, "locked")]
    guard = ReadinessGuard(_Inner(), lambda: seq.pop(0), min_interval_s=2.0,
                           clock=lambda: clock[0])
    assert guard.state() is RunControl.RUNNING
    clock[0] += 2.1
    assert guard.state() is RunControl.STOPPING


def test_guard_denies_approval_against_an_unseeable_desktop():
    inner = _Inner()
    guard = ReadinessGuard(inner, lambda: rd.Readiness(rd.LOCKED, "workstation locked"))
    resolution = guard.request_approval(_request(), 0.01)
    assert resolution.decision.value == "deny" and resolution.auto is True
    assert "locked" in resolution.reason
    assert inner.approvals == 0   # never forwarded: nobody may approve a blind action


def test_guard_survives_a_failing_probe_without_killing_a_healthy_run():
    def boom():
        raise RuntimeError("probe exploded")
    guard = ReadinessGuard(_Inner(), boom, min_interval_s=0.0)
    assert guard.state() is RunControl.RUNNING   # observability must not kill execution
    assert guard.lost_readiness is None


def test_guard_notifies_once_when_readiness_is_lost():
    seen = []
    guard = ReadinessGuard(_Inner(), lambda: rd.Readiness(rd.LOGGED_OUT, "gone"),
                           on_lost=seen.append, min_interval_s=0.0)
    guard.state()
    guard.state()
    assert len(seen) == 1 and seen[0].state == rd.LOGGED_OUT
