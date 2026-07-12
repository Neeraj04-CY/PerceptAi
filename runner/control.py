"""RemoteControlChannel — Sprint 3's ControlChannel, over the network.

The engine reads control at its per-cycle checkpoint through the abstract
ControlChannel surface (state / wait_for_change / request_approval). Locally
that surface is an in-process ThreadedControlChannel; on a runner it is this:
the same three methods, backed by long-polls to the control plane's durable
control record. The runtime is unchanged and never learns that pause, resume,
stop and approval are crossing a wire.

Fail-open on transient transport errors: a momentarily unreachable plane reads
as 'running' rather than blocking a healthy run — the next checkpoint re-reads,
so a real stop is never lost, only briefly delayed.
"""
from __future__ import annotations

import time
from typing import Protocol

from typing import Callable, Optional

from perceptai.contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolution,
    RunControl,
)
from perceptai.control import ControlChannel

_STATE = {"paused": RunControl.PAUSED, "stopping": RunControl.STOPPING}


class ControlTransport(Protocol):
    def get_control(self, session_id: str) -> dict: ...
    def post_approval_request(self, session_id: str, request: dict) -> None: ...


class RemoteControlChannel(ControlChannel):
    def __init__(self, client: ControlTransport, session_id: str,
                 *, poll_interval_s: float = 1.0):
        self._client = client
        self._sid = session_id
        self._poll = poll_interval_s

    def _read_state(self) -> str:
        try:
            return (self._client.get_control(self._sid) or {}).get("state", "running")
        except Exception:
            return "running"  # fail-open; the next checkpoint re-reads

    def state(self) -> RunControl:
        return _STATE.get(self._read_state(), RunControl.RUNNING)

    def wait_for_change(self, timeout_s: float) -> RunControl:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            s = self._read_state()
            if s != "paused":
                return _STATE.get(s, RunControl.RUNNING)
            time.sleep(min(self._poll, max(0.0, deadline - time.time())))
        return RunControl.PAUSED

    def request_approval(self, request: ApprovalRequest,
                         timeout_s: float) -> ApprovalResolution:
        try:
            self._client.post_approval_request(self._sid, request.to_dict())
        except Exception:
            pass  # the operator can still see the request via the live event
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                control = self._client.get_control(self._sid) or {}
            except Exception:
                control = {}
            decision = control.get("approval_decision")
            if decision and str(decision.get("request_id")) == str(request.request_id):
                granted = decision.get("decision") == "grant"
                return ApprovalResolution(
                    decision=ApprovalDecision.GRANT if granted else ApprovalDecision.DENY,
                    decided_by=decision.get("decided_by", ""),
                    reason=decision.get("reason", ""),
                )
            time.sleep(min(self._poll, max(0.0, deadline - time.time())))
        return ApprovalResolution(
            decision=ApprovalDecision.DENY, auto=True, reason="approval request timed out")


class ReadinessGuard(ControlChannel):
    """Session truth, enforced mid-run — as a ControlChannel, not a new seam.

    Wraps any control channel (local or remote). If the desktop is lost while a
    run is in flight (the workstation locks, the RDP session drops, the console
    logs out), the engine's next control checkpoint reads STOPPING and the run
    ends honestly — instead of clicking blindly at a lock screen and reporting
    inscrutable perception failures.

    The engine is unchanged and never learns why it was stopped: it sees the
    same STOPPING it sees when an operator presses the button. The runner
    records the readiness state that caused it, so the failure explains itself
    to the human who reads it in the morning.

    Approval under a lost desktop is denied outright: an approval that could
    only be acted on by driving a screen we cannot see must never be granted.

    The probe is THROTTLED: the engine calls state() at every control checkpoint
    (many times per cycle), while the real probe touches Win32 and the display.
    Session truth needs to be noticed within a second or two, not on every
    checkpoint — so we cache for `min_interval_s` and keep the checkpoint free.
    """

    def __init__(self, inner: ControlChannel,
                 readiness_probe: Callable[[], object],
                 *, on_lost: Optional[Callable[[object], None]] = None,
                 min_interval_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic):
        self._inner = inner
        self._probe = readiness_probe
        self._on_lost = on_lost
        self._lost: Optional[object] = None
        self._min_interval = min_interval_s
        self._clock = clock
        self._last_check: Optional[float] = None

    @property
    def lost_readiness(self) -> Optional[object]:
        """The readiness state that stopped the run, if any (for the report)."""
        return self._lost

    def _desktop_lost(self) -> bool:
        if self._lost is not None:
            return True  # latched: never flap back to running mid-run
        now = self._clock()
        if self._last_check is not None and (now - self._last_check) < self._min_interval:
            return False                      # recently checked; keep the checkpoint cheap
        self._last_check = now
        try:
            readiness = self._probe()
        except Exception:
            return False  # a failing probe must not kill a healthy run
        if getattr(readiness, "can_execute", True):
            return False
        self._lost = readiness
        if self._on_lost is not None:
            try:
                self._on_lost(readiness)
            except Exception:
                pass
        return True

    def state(self) -> RunControl:
        if self._desktop_lost():
            return RunControl.STOPPING
        return self._inner.state()

    def wait_for_change(self, timeout_s: float) -> RunControl:
        if self._desktop_lost():
            return RunControl.STOPPING
        return self._inner.wait_for_change(timeout_s)

    def request_approval(self, request: ApprovalRequest,
                         timeout_s: float) -> ApprovalResolution:
        if self._desktop_lost():
            readiness = self._lost
            state = getattr(readiness, "state", "unknown")
            return ApprovalResolution(
                decision=ApprovalDecision.DENY, auto=True,
                reason=f"the execution environment became unavailable ({state}); "
                       "no action may be approved against a desktop we cannot see")
        return self._inner.request_approval(request, timeout_s)
