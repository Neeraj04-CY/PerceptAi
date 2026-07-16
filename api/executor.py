"""Adapter between the API layer and the unified PerceptAI engine.

This module contains NO execution logic. It creates AgentSessions and
Workforces, relays the canonical event stream in wire formats owned by
perceptai.streaming, and returns structured results. On hosts without
desktop dependencies (e.g. cloud deploys) it degrades to a structured
error instead of crashing the server.

Both streams capture the canonical events they relay (bounded) and hand
them back on the final "_result" item so the HTTP layer can persist them
for replay — the API layer never rebuilds events.
"""
from __future__ import annotations

import queue
import sys
import threading
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Callable, Generator, Optional, Tuple

# The engine package lives at the repository root, one level above api/.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Canonical events kept per run for replay persistence. Beyond the cap the
# run still streams live; only the stored history is truncated.
EVENT_CAP = 2000

# Server-level registry of the most recent session (for /screenshot).
# This is API infrastructure state, not engine execution state.
_registry_lock = threading.Lock()
_last_session = None


def _load_engine():
    try:
        from perceptai import AgentSession, EngineConfig
        from perceptai.streaming import legacy_steps, to_legacy_sse
        return AgentSession, EngineConfig, to_legacy_sse, legacy_steps, None
    except Exception as e:  # missing desktop deps on this host
        return None, None, None, None, f"Engine unavailable on this host: {e}"


def engine_available() -> Tuple[bool, str]:
    """Whether this host can execute (imports resolve). Used by health."""
    *_, err = _load_engine()
    return err is None, err or ""


def _engine_config(EngineConfig):
    engine_config = EngineConfig.from_env()
    if not engine_config.groq_api_key:
        from config import config as api_config
        engine_config.groq_api_key = api_config.GROQ_API_KEY or ""
    return engine_config


def _make_session(AgentSession, EngineConfig, *, control=None, overrides=None,
                  secrets=None, egress=None, memory=None):
    global _last_session
    config = _engine_config(EngineConfig)
    for key, value in (overrides or {}).items():
        if value not in (None, ""):
            setattr(config, key, value)
    kwargs = {}
    if control is not None:
        kwargs["control"] = control
    if secrets is not None:
        kwargs["secrets"] = secrets
    if memory is not None:
        # Business Memory: the org's compounding lessons, injected through the
        # engine's EXISTING recall seam (an OrgMemoryStore decorator). The
        # engine stays transport-independent and unchanged.
        kwargs["memory"] = memory
    if egress is not None:
        # Workspace data-egress policy (as data), enforced at the engine's ONE
        # LLM checkpoint — identically for local and remote runs.
        from perceptai.egress import EgressGuard, EgressPolicy
        kwargs["egress"] = EgressGuard(EgressPolicy.from_dict(egress))
    session = AgentSession(config, **kwargs)
    with _registry_lock:
        _last_session = session
    return session


def latest_screenshot_path() -> Optional[Path]:
    with _registry_lock:
        session = _last_session
    if session is None:
        return None
    try:
        return session.perception.latest_screenshot
    except Exception:
        return None


def _relay(events_bus, run: Callable[[], object],
           serialize: Callable) -> Generator:
    """Shared streaming loop: run on a worker thread, relay every canonical
    event through `serialize`, capture raw events (bounded), and finish by
    yielding (result, captured_events). The ONE relay both streams use."""
    event_queue: queue.Queue = queue.Queue()
    events_bus.subscribe(event_queue.put)
    holder: dict = {}
    captured: list[dict] = []

    def _run():
        try:
            holder["result"] = run()
        except Exception as e:
            event_queue.put({"type": "error", "message": str(e)})
        finally:
            event_queue.put(None)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    while True:
        item = event_queue.get()
        if item is None:
            break
        if isinstance(item, dict):  # adapter-level error marker
            yield item
            continue
        if len(captured) < EVENT_CAP:
            captured.append(item.to_dict())
        wire = serialize(item)
        if wire is not None:
            yield wire

    yield ("_done", holder.get("result"), captured)


def execute_task(instruction: str) -> Tuple[Optional[object], Optional[str]]:
    """Run one task synchronously. Returns (TaskResult, None) or (None, error)."""
    AgentSession, EngineConfig, _, _, err = _load_engine()
    if err:
        return None, err
    session = _make_session(AgentSession, EngineConfig)
    try:
        return session.run(instruction), None
    except Exception as e:
        return None, str(e)


def execute_task_stream(instruction: str, *, control=None,
                        approval_risk_threshold: str = "",
                        secrets=None, egress=None,
                        memory=None, overrides=None) -> Generator[dict, None, None]:
    """Run one task, yielding dashboard-format SSE dicts as events happen.

    `control` is an optional perceptai ControlChannel (from the API's control
    registry) that makes the run pausable/stoppable and gates risky actions on
    approval; `approval_risk_threshold` is the workspace risk policy (as data)
    that decides when approval is required; `egress` is the workspace's
    data-egress policy (as data), governing what may leave this machine. The
    final yielded item has type "_result" carrying the full TaskResult plus the
    captured canonical events; the HTTP layer persists both and must not
    forward them to clients.
    """
    AgentSession, EngineConfig, to_legacy_sse, legacy_steps, err = _load_engine()
    if err:
        yield {"type": "error", "message": err}
        return

    session = _make_session(
        AgentSession, EngineConfig, control=control, secrets=secrets, egress=egress,
        memory=memory,
        overrides={**(overrides or {}),
                   "approval_risk_threshold": approval_risk_threshold},
    )
    for item in _relay(session.events, lambda: session.run(instruction),
                       to_legacy_sse):
        if isinstance(item, tuple):
            _, result, captured = item
            if result is not None:
                yield {
                    "type": "_result",
                    "result": result.to_dict(),
                    "steps": legacy_steps(result),
                    "status": result.status.value,
                    "execution_time": result.duration_s,
                    "error": "; ".join(result.errors) if result.errors else None,
                    "events": captured,
                }
            return
        yield item


def execute_mission_stream(
    instruction: str,
    *,
    workspace: Optional[dict] = None,
    limits: Optional[dict] = None,
    approver=None,
) -> Generator[dict, None, None]:
    """Run one workforce mission, yielding wire-v1 SSE dicts (canonical
    event types with nested `data`). `workspace` and `limits` are plain
    dicts from the control plane, mapped onto the engine's typed
    WorkspaceContext / WorkforceLimits. The final "_result" item carries
    the MissionResult and captured events for persistence.
    """
    try:
        from perceptai import EngineConfig
        from perceptai.streaming import to_platform_sse
        from perceptai.workforce import (
            MissionPolicy,
            Workforce,
            WorkforceConfig,
            WorkforceLimits,
            WorkspaceContext,
        )
    except Exception as e:
        yield {"type": "error", "message": f"Engine unavailable on this host: {e}"}
        return

    config = WorkforceConfig(engine=_engine_config(EngineConfig))
    ws = WorkspaceContext(**_dataclass_kwargs(WorkspaceContext, workspace or {}))
    wl = WorkforceLimits(**_dataclass_kwargs(WorkforceLimits, limits or {})) \
        if limits else WorkforceLimits.for_plan(ws.plan)

    # Plan limits bound the mission loop itself, not just per-order policy.
    config.max_parallel = wl.max_parallel
    config.max_work_orders = wl.max_work_orders
    config.max_mission_duration_s = wl.max_mission_duration_s
    config.max_total_cost = wl.max_total_cost

    policy = MissionPolicy(limits=wl, workspace=ws, approver=approver)
    workforce = Workforce(config, policy=policy)

    for item in _relay(workforce.events,
                       lambda: workforce.run_mission(instruction),
                       to_platform_sse):
        if isinstance(item, tuple):
            _, result, captured = item
            if result is not None:
                yield {
                    "type": "_result",
                    "result": result.to_dict(),
                    "status": result.status.value,
                    "metrics": result.metrics.to_dict(),
                    "execution_time": result.duration_s,
                    "error": "; ".join(result.errors) if result.errors else None,
                    "events": captured,
                }
            return
        yield item


def _dataclass_kwargs(cls, values: dict) -> dict:
    """Keep only keys the dataclass declares — control-plane dicts may
    carry extra metadata without breaking the engine contract."""
    names = {f.name for f in dataclass_fields(cls)}
    return {k: v for k, v in values.items() if k in names}
