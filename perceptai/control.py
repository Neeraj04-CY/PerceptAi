"""The control channel — the trust layer's interruptibility surface.

The engine reads control state at its existing per-cycle checkpoint; it
never grows a second loop. The channel is transport-agnostic on purpose:
the default is a pass-through (a run behaves exactly as before the trust
layer existed), an in-process implementation backs the API's control
endpoints, and the same interface is what a future remote runner speaks.

Concurrency lives in exactly one place — `ThreadedControlChannel` — so
the API registry and the tests share one control state machine rather
than each re-deriving the tricky condition-variable logic.
"""
from __future__ import annotations

import threading
from typing import Optional

from .contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolution,
    RunControl,
)


class ControlChannel:
    """Pass-through control. No attached controller means the run is never
    paused, never stopped from outside, and never gated on approval — it
    behaves exactly as it did before the trust layer existed.

    The engine calls three read/wait primitives; a controller (API, future
    runner) subclasses this and drives them from the outside."""

    # -- engine side (read at the per-cycle checkpoint / before a risky step) --

    def state(self) -> RunControl:
        return RunControl.RUNNING

    def wait_for_change(self, timeout_s: float) -> RunControl:
        """Block while PAUSED; return the new state when it clears (RUNNING),
        when stopped (STOPPING), or PAUSED if the wait budget elapsed."""
        return RunControl.RUNNING

    def request_approval(self, request: ApprovalRequest,
                         timeout_s: float) -> ApprovalResolution:
        """Deny by default: a policy asked for approval but no approver is
        attached. Honest failure over blind action — the caller plans around
        the denial. This only fires when a workspace sets an approval
        threshold; with gating off it is never called."""
        return ApprovalResolution(
            decision=ApprovalDecision.DENY, auto=True,
            reason="no approver attached to this execution",
        )


class ThreadedControlChannel(ControlChannel):
    """Thread-safe control state machine. The engine runs on one thread and
    reads state; the API (or a test) drives pause/resume/stop and approval
    decisions from another. One condition variable coordinates both sides."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._state = RunControl.RUNNING
        self._pending: Optional[ApprovalRequest] = None
        self._resolution: Optional[ApprovalResolution] = None

    # ------------------------------------------------ controller (outside) side

    def pause(self) -> None:
        with self._cond:
            if self._state == RunControl.RUNNING:
                self._state = RunControl.PAUSED
                self._cond.notify_all()

    def resume(self) -> None:
        with self._cond:
            if self._state == RunControl.PAUSED:
                self._state = RunControl.RUNNING
                self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            self._state = RunControl.STOPPING
            self._cond.notify_all()

    def resolve_approval(self, request_id: str, decision: ApprovalDecision,
                         decided_by: str = "", reason: str = "") -> bool:
        """Settle the pending approval if the id matches. Returns False when
        there is nothing pending or the id is stale."""
        with self._cond:
            if self._pending is None or self._pending.request_id != request_id:
                return False
            self._resolution = ApprovalResolution(
                decision=decision, decided_by=decided_by, reason=reason,
            )
            self._cond.notify_all()
            return True

    def pending_approval(self) -> Optional[ApprovalRequest]:
        with self._cond:
            return self._pending

    def snapshot(self) -> dict:
        """A plain view for a status endpoint."""
        with self._cond:
            return {
                "state": self._state.value,
                "pending_approval": self._pending.to_dict() if self._pending else None,
            }

    # ------------------------------------------------------------- engine side

    def state(self) -> RunControl:
        with self._cond:
            return self._state

    def wait_for_change(self, timeout_s: float) -> RunControl:
        with self._cond:
            self._cond.wait_for(
                lambda: self._state != RunControl.PAUSED, timeout=timeout_s,
            )
            return self._state

    def request_approval(self, request: ApprovalRequest,
                         timeout_s: float) -> ApprovalResolution:
        with self._cond:
            self._pending = request
            self._resolution = None
            self._cond.notify_all()
            self._cond.wait_for(
                lambda: self._resolution is not None
                or self._state == RunControl.STOPPING,
                timeout=timeout_s,
            )
            if self._resolution is not None:
                res = self._resolution
            elif self._state == RunControl.STOPPING:
                res = ApprovalResolution(
                    decision=ApprovalDecision.DENY, auto=True,
                    reason="execution stopped before approval",
                )
            else:
                res = ApprovalResolution(
                    decision=ApprovalDecision.DENY, auto=True,
                    reason="approval request timed out",
                )
            self._pending = None
            self._resolution = None
            return res
