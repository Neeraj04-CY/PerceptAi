"""The runner work loop — thin by design.

register (done out-of-band) -> long-poll claim -> verify signed order ->
execute through ONE AgentSession -> stream wire-v1 events back -> report
result -> repeat. Heartbeats run on their own thread and renew the lease.

The engine is unchanged and transport-unaware: the worker only SUBSCRIBES to
the session's canonical EventBus and forwards what it emits, and (Step 3)
injects a ControlChannel that reads control over the network. No planning, no
execution logic, no second loop lives here.

The client and the session factory are injected, so the whole loop runs
against a fake transport and a simulated runtime in tests — no network, no
real screen.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Optional, Protocol

from ._signing import verify_work_order
from .config import RunnerConfig


class ControlPlane(Protocol):
    """The transport surface the worker needs. The HTTP client implements it;
    tests inject a fake."""
    def heartbeat(self, current_session_id: Optional[str]) -> None: ...
    def claim(self) -> Optional[dict]: ...  # signed work order, or None
    def post_events(self, session_id: str, events: list[dict]) -> None: ...
    def post_result(self, session_id: str, report: dict) -> None: ...
    def get_control(self, session_id: str) -> dict: ...
    def post_approval_request(self, session_id: str, request: dict) -> None: ...


# A factory that builds an execution session for one instruction. Injected so
# tests can supply a simulated session; production builds a real AgentSession.
SessionFactory = Callable[[str], Any]
# Builds the ControlChannel for a session (Step 3 injects the remote one).
ControlFactory = Callable[[str], Any]


class EventPump:
    """Forwards a session's canonical events to the plane as wire-v1 batches.

    The subscriber runs in the engine thread and only enqueues (fast, never
    blocks execution on the network); a background thread flushes batches on a
    latency budget. Send failures re-enqueue — the plane's ingest is
    idempotent on seq, so retries never duplicate."""

    def __init__(self, bus, send: Callable[[list[dict]], bool],
                 flush_interval_s: float, batch_max: int):
        from perceptai.streaming import to_platform_sse
        self._to_wire = to_platform_sse
        self._bus = bus
        self._send = send
        self._flush_interval = flush_interval_s
        self._batch_max = batch_max
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _on_event(self, event) -> None:
        # Engine-thread hot path: serialize + enqueue only.
        self._q.put(self._to_wire(event))

    def start(self) -> None:
        self._bus.subscribe(self._on_event)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _drain(self, timeout: float) -> list[dict]:
        batch: list[dict] = []
        try:
            batch.append(self._q.get(timeout=timeout))
        except queue.Empty:
            return batch
        while len(batch) < self._batch_max:
            try:
                batch.append(self._q.get_nowait())
            except queue.Empty:
                break
        return batch

    def _flush(self, batch: list[dict]) -> None:
        if batch and not self._send(batch):
            for e in batch:            # send failed — retry next cycle (plane dedups)
                self._q.put(e)
            time.sleep(0.5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._flush(self._drain(self._flush_interval))

    def stop(self) -> None:
        """Detach the subscriber, flush everything still queued, then stop."""
        self._bus.unsubscribe(self._on_event)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        batch = self._drain(0)
        while batch:
            self._flush(batch)
            batch = self._drain(0)


class Worker:
    def __init__(self, client: ControlPlane, config: RunnerConfig,
                 session_factory: Optional[SessionFactory] = None,
                 control_factory: Optional[ControlFactory] = None):
        self._client = client
        self._config = config
        self._session_factory = session_factory or _default_session_factory
        self._control_factory = control_factory
        self._current_session_id: Optional[str] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------ lifecycle

    def run_forever(self) -> None:
        """Heartbeat on a side thread; claim/execute on the main thread until
        stopped. Bounded backoff keeps an idle runner cheap and a disconnected
        one from hammering the plane."""
        hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb.start()
        backoff = self._config.poll_interval_s
        while not self._stop.is_set():
            try:
                signed = self._client.claim()
            except Exception:
                signed = None
                time.sleep(min(backoff, self._config.reconnect_max_s))
                backoff = min(backoff * 2, self._config.reconnect_max_s)
                continue
            if signed is None:
                time.sleep(backoff)
                backoff = min(backoff * 2, self._config.poll_max_interval_s)
                continue
            backoff = self._config.poll_interval_s
            self.execute_work_order(signed)

    def stop(self) -> None:
        self._stop.set()

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                sid = self._current_session_id
            try:
                self._client.heartbeat(sid)
            except Exception:
                pass  # a missed heartbeat is recoverable; the loop retries
            self._stop.wait(self._config.heartbeat_interval_s)

    # -------------------------------------------------------------- execute

    def execute_work_order(self, signed: dict) -> dict:
        """Verify, then run one order end to end. Returns the report it sent
        (for tests/observability). Never raises into the loop: a bad order is
        reported as a failure and the runner stays alive."""
        order = signed.get("work_order") or {}
        signature = signed.get("signature") or ""
        session_id = str(order.get("session_id") or "")

        if not verify_work_order(self._config.signing_key, order, signature):
            report = {"status": "failed", "result": None, "steps": [],
                      "execution_time": 0.0,
                      "error": "work order signature verification failed", "events": []}
            if session_id:
                self._safe_post_result(session_id, report)
            return report

        with self._lock:
            self._current_session_id = session_id
        try:
            return self._run(session_id, str(order.get("instruction", "")), order)
        finally:
            with self._lock:
                self._current_session_id = None

    def _run(self, session_id: str, instruction: str, order: dict) -> dict:
        from perceptai.streaming import legacy_steps

        session = self._session_factory(instruction)
        # Apply the workspace risk policy carried in the signed order, so a
        # remote run gates on approval exactly like a local one (the shared
        # config object is what the RiskAssessor reads).
        threshold = str(order.get("approval_risk_threshold", "") or "")
        if threshold:
            session.config.approval_risk_threshold = threshold
        if self._control_factory is not None:
            # Swap the pass-through channel for the remote one.
            session.control = self._control_factory(session_id)

        pump = EventPump(
            session.events,
            lambda batch: self._safe_post_events(session_id, batch),
            self._config.event_flush_interval_s, self._config.event_batch_max,
        )
        pump.start()
        try:
            result = session.run(instruction)
            report = {
                "status": result.status.value,
                "result": result.to_dict(),
                "steps": legacy_steps(result),
                "execution_time": result.duration_s,
                "error": "; ".join(result.errors) if result.errors else None,
                "events": [],
            }
        except Exception as e:
            report = {"status": "failed", "result": None, "steps": [],
                      "execution_time": 0.0, "error": str(e), "events": []}
        finally:
            pump.stop()

        self._safe_post_result(session_id, report)
        return report

    # --------------------------------------------------------------- io glue

    def _safe_post_events(self, session_id: str, batch: list[dict]) -> bool:
        try:
            self._client.post_events(session_id, batch)
            return True
        except Exception:
            return False

    def _safe_post_result(self, session_id: str, report: dict) -> None:
        try:
            self._client.post_result(session_id, report)
        except Exception:
            pass  # the plane reclaims the lease on timeout; the run is not lost silently


def _default_session_factory(instruction: str):
    """Production: one real AgentSession per work order (one runtime, no fork)."""
    from perceptai import AgentSession, EngineConfig
    return AgentSession(EngineConfig.from_env())
