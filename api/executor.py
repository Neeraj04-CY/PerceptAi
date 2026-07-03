"""Adapter between the API layer and the unified PerceptAI engine.

This module contains NO execution logic. It creates AgentSessions,
relays the canonical event stream in the dashboard wire format, and
returns structured TaskResults. On hosts without desktop dependencies
(e.g. cloud deploys) it degrades to a structured error instead of
crashing the server.
"""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Generator, Optional, Tuple

# The engine package lives at the repository root, one level above api/.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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


def _make_session(AgentSession, EngineConfig):
    global _last_session
    engine_config = EngineConfig.from_env()
    if not engine_config.groq_api_key:
        from config import config as api_config
        engine_config.groq_api_key = api_config.GROQ_API_KEY or ""
    session = AgentSession(engine_config)
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


def execute_task_stream(instruction: str) -> Generator[dict, None, None]:
    """Run one task, yielding dashboard-format SSE dicts as events happen.

    The final yielded item has type "_result" carrying the full TaskResult;
    the HTTP layer persists it and must not forward it to clients.
    """
    AgentSession, EngineConfig, to_legacy_sse, legacy_steps, err = _load_engine()
    if err:
        yield {"type": "error", "message": err}
        return

    session = _make_session(AgentSession, EngineConfig)
    event_queue: queue.Queue = queue.Queue()
    session.events.subscribe(event_queue.put)
    holder: dict = {}

    def _run():
        try:
            holder["result"] = session.run(instruction)
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
        sse = to_legacy_sse(item)
        if sse is not None:
            yield sse

    result = holder.get("result")
    if result is not None:
        yield {
            "type": "_result",
            "result": result.to_dict(),
            "steps": legacy_steps(result),
            "status": result.status.value,
            "execution_time": result.duration_s,
            "error": "; ".join(result.errors) if result.errors else None,
        }
