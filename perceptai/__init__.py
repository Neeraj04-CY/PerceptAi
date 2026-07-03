"""PerceptAI — universal perception layer for AI agents.

Public API:

    from perceptai import AgentSession, EngineConfig

    session = AgentSession()
    result = session.run("open notepad and type hello")
    print(result.summary)
"""
from .config import EngineConfig
from .contracts import (
    ActionType,
    Artifact,
    Evidence,
    GoalSpec,
    Step,
    StepResult,
    StepStatus,
    Task,
    TaskContext,
    TaskReport,
    TaskResult,
    TaskStatus,
    VerificationResult,
)
from .events import EventBus, EventType, TaskEvent
from .session import AgentSession

__version__ = "0.2.0"

__all__ = [
    "AgentSession",
    "EngineConfig",
    "EventBus",
    "EventType",
    "TaskEvent",
    "Task",
    "TaskContext",
    "TaskResult",
    "TaskStatus",
    "Step",
    "StepResult",
    "StepStatus",
    "ActionType",
    "Evidence",
    "GoalSpec",
    "TaskReport",
    "Artifact",
    "VerificationResult",
]
