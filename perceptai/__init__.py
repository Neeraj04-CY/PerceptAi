"""PerceptAI — universal perception layer for AI agents.

Public API:

    from perceptai import AgentSession, EngineConfig

    session = AgentSession()
    result = session.run("open notepad and type hello")
    print(result.summary)

Mission-level execution (the AI Workforce OS) lives in the subpackage:

    from perceptai.workforce import Workforce

    result = Workforce().run_mission("Research Stripe pricing")
    print(result.report.executive_summary)
"""
from .config import EngineConfig
from .contracts import (
    ActionType,
    Artifact,
    Belief,
    BoundingBox,
    BudgetSnapshot,
    Decision,
    DecisionType,
    Evidence,
    GoalSpec,
    Hypothesis,
    Observation,
    ProgressEstimate,
    ProviderReport,
    SourceType,
    Step,
    StepResult,
    StepStatus,
    StrategyProfile,
    Task,
    TaskContext,
    TaskReport,
    TaskResult,
    TaskStatus,
    UIElement,
    UncertaintySignal,
    VerificationResult,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from .events import EventBus, EventType, TaskEvent
from .providers import FrameContext, PerceptionProvider
from .reasoning import ReasoningEngine
from .session import AgentSession
from .strategy import StrategyManager
from .world import WorldModel

__version__ = "0.5.0"

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
    # Adaptive Reasoning Engine
    "ReasoningEngine",
    "StrategyManager",
    "Belief",
    "Hypothesis",
    "UncertaintySignal",
    "ProgressEstimate",
    "Decision",
    "DecisionType",
    "StrategyProfile",
    "BudgetSnapshot",
]
