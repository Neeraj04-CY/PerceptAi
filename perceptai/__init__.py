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
    BoundingBox,
    Evidence,
    GoalSpec,
    Observation,
    ProviderReport,
    SourceType,
    Step,
    StepResult,
    StepStatus,
    Task,
    TaskContext,
    TaskReport,
    TaskResult,
    TaskStatus,
    UIElement,
    VerificationResult,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from .events import EventBus, EventType, TaskEvent
from .providers import FrameContext, PerceptionProvider
from .session import AgentSession
from .world import WorldModel

__version__ = "0.3.0"

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
    # Universal Perception Layer
    "WorldModel",
    "WorldState",
    "WorldDiff",
    "UIElement",
    "WindowInfo",
    "Observation",
    "SourceType",
    "BoundingBox",
    "ProviderReport",
    "PerceptionProvider",
    "FrameContext",
]
