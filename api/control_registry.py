"""In-process registry of live execution control channels.

This is API infrastructure state (like executor._last_session), not engine
execution state: it maps a running execution id to the ThreadedControlChannel
the engine reads at its per-cycle checkpoint. The control endpoints look a
channel up here to pause/resume/stop or settle an approval.

Single-process, single-host by design — execution happens on the machine
hosting the API, and a control request must reach the same process. The
ControlChannel interface is the seam a future control-plane + remote-runner
split extends into; the registry becomes a routing table to remote channels
without the engine or the endpoints changing shape.

Crash / restart semantics (in-process model)
--------------------------------------------
Control state is in-memory and shares the lifetime of the execution it
governs — the run and its channel live in the same process:

* A crash or restart tears down the execution thread AND this registry
  together. A *paused* run does not survive; there is no persisted "paused"
  checkpoint to resume from. This is intentional for the local-runner model:
  a run is bound to the host executing it.
* The session row is left as-is (status ``running``): the completion
  writeback runs in the stream's ``finally`` and never executed. The run is
  orphaned, not silently marked done — honest over a fabricated outcome.
* After restart the registry is empty, so control/approval calls for that
  session return HTTP 409 ("not live"); the cockpit reads this as "execution
  finished" and the operator starts a fresh run. Stale ``running`` rows are
  reconciled by ordinary session housekeeping, not by this module.
* ``max_pause_s`` / ``max_approval_wait_s`` are within-process guarantees
  (the parked engine thread wakes and ends honestly); they do not span a
  restart, because the process and its timers are gone.

Durable pause/resume across restarts is deliberately a control-plane
responsibility in the remote-runner design: control state moves to the DB,
decoupled from the execution host. That migration does not change the
ControlChannel interface — only this registry becomes a lookup into
persisted/remote channels.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perceptai.control import ThreadedControlChannel  # noqa: E402


class ControlRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[str, ThreadedControlChannel] = {}

    def open(self, execution_id: str) -> ThreadedControlChannel:
        channel = ThreadedControlChannel()
        with self._lock:
            self._channels[execution_id] = channel
        return channel

    def get(self, execution_id: str) -> Optional[ThreadedControlChannel]:
        with self._lock:
            return self._channels.get(execution_id)

    def close(self, execution_id: str) -> None:
        with self._lock:
            self._channels.pop(execution_id, None)


_registry = ControlRegistry()


def registry() -> ControlRegistry:
    return _registry
