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
