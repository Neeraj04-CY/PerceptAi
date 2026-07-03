"""AgentSession — the composition root of the runtime.

A session owns everything a task run needs: configuration, workspace,
LLM client, perception, actions, OS control, planner, healer, verifier,
memory and the event bus. Nothing execution-related lives at module
level; two sessions never share mutable state.

All services are constructor-injectable for testing.
"""
from __future__ import annotations

import uuid
from typing import Optional, Union

from .actions import ActionExecutor
from .config import EngineConfig
from .contracts import Task, TaskResult
from .events import EventBus, EventType
from .healer import Healer
from .llm import LLMClient
from .memory import MemoryStore
from .oscontrol import AppLauncher, WindowManager
from .perception import PerceptionService
from .planner import Planner
from .verification import Verifier


class AgentSession:
    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        *,
        events: Optional[EventBus] = None,
        llm: Optional[LLMClient] = None,
        windows: Optional[WindowManager] = None,
        perception: Optional[PerceptionService] = None,
        apps: Optional[AppLauncher] = None,
        actions: Optional[ActionExecutor] = None,
        planner: Optional[Planner] = None,
        healer: Optional[Healer] = None,
        verifier: Optional[Verifier] = None,
        memory: Optional[MemoryStore] = None,
    ):
        self.config = config or EngineConfig.from_env()
        self.id = str(uuid.uuid4())
        self.workspace = self.config.workspace_root / self.id[:8]

        self.events = events or EventBus()
        self.llm = llm or LLMClient(self.config.groq_api_key)
        self.windows = windows or WindowManager()
        self.perception = perception or PerceptionService(self.config, self.llm, self.workspace)
        self.apps = apps or AppLauncher(self.config, self.windows)
        self.actions = actions or ActionExecutor(self.config)
        self.planner = planner or Planner(self.config, self.llm)
        self.healer = healer or Healer(self.config, self.llm)
        self.verifier = verifier or Verifier(self.windows)
        self.memory = memory or MemoryStore(self.config.memory_db_path)

    def emit(self, type: EventType, task: Task, **payload) -> None:
        self.events.emit(type, session_id=self.id, task_id=task.id, **payload)

    def run(self, task: Union[Task, str]) -> TaskResult:
        """Execute one task to completion and return its structured result."""
        from .runtime import ExecutionEngine

        if isinstance(task, str):
            task = Task(instruction=task)
        return ExecutionEngine(self).run(task)
