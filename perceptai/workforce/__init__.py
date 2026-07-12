"""The AI Workforce Operating System (Chapter 5).

One mission in, one grounded business deliverable out. The Workforce
facade composes the kernel (Chapters 1-4) with the workforce layer:
registry + built-in specialists, runner pool (one shared AgentSession
per desktop), mission planner, deterministic scheduler, policy and
organizational experience.

    from perceptai.workforce import Workforce
    result = Workforce().run_mission("Research Stripe pricing")

Everything is constructor-injectable; the simulation substrate builds a
fully simulated workforce for tests and evals/workforce_bench.py.
"""
from __future__ import annotations

from typing import Optional, Union

from ..config import EngineConfig
from ..events import EventBus
from ..goal import GoalAnalyzer
from ..llm import LLMClient
from ..memory import MemoryStore
from ..reporting import ReportBuilder
from .contracts import (  # noqa: F401
    Mission,
    MissionDecision,
    MissionDecisionType,
    MissionMetrics,
    MissionResult,
    MissionStatus,
    SpecialistProfile,
    WorkforceConfig,
    WorkOrder,
    WorkResult,
    WorkStatus,
)
from .evidence_graph import EvidenceGraph  # noqa: F401
from .executive import ExecutiveOrchestrator  # noqa: F401
from .experience import ExperienceStore  # noqa: F401
from .graph import WorkGraph  # noqa: F401
from .planner import MissionPlanner  # noqa: F401
from .policy import (  # noqa: F401
    AuditLog,
    MissionPolicy,
    WorkforceLimits,
    WorkspaceContext,
)
from .registry import SpecialistRegistry  # noqa: F401
from .scheduler import MissionScheduler, RunnerPool  # noqa: F401
from .specialist import (  # noqa: F401
    EvidenceReviewSpecialist,
    MemoryRecallSpecialist,
    MissionContext,
    RuntimeSpecialist,
    Specialist,
    builtin_specialists,
)


class Workforce:
    """Composition root of the workforce — the mission-level counterpart
    of AgentSession. Owns the registry, runners, planner, scheduler,
    policy, experience and event bus; every service is injectable."""

    def __init__(
        self,
        config: Optional[Union[WorkforceConfig, EngineConfig]] = None,
        *,
        events: Optional[EventBus] = None,
        llm: Optional[LLMClient] = None,
        registry: Optional[SpecialistRegistry] = None,
        runners: Optional[RunnerPool] = None,
        planner: Optional[MissionPlanner] = None,
        scheduler: Optional[MissionScheduler] = None,
        policy: Optional[MissionPolicy] = None,
        memory: Optional[MemoryStore] = None,
        experience: Optional[ExperienceStore] = None,
        goal_analyzer=None,
        reporter=None,
        discover_plugins: bool = True,
    ):
        if config is None:
            self.config = WorkforceConfig(engine=EngineConfig.from_env())
        elif isinstance(config, EngineConfig):
            self.config = WorkforceConfig(engine=config)
        else:
            self.config = config
        engine = self.config.engine

        self.events = events or EventBus()
        self.llm = llm or LLMClient(engine)
        self.memory = memory or MemoryStore(engine.memory_db_path)
        self.experience = experience or ExperienceStore(engine.memory_db_path)
        self.policy = policy or MissionPolicy()
        self.runners = runners or RunnerPool(self._session_factory)

        self.registry = registry or SpecialistRegistry()
        if registry is None:
            for specialist in builtin_specialists(self.runners):
                self.registry.register(specialist)
            if discover_plugins:
                self.registry.discover()

        self.planner = planner or MissionPlanner(self.config, self.llm)
        self.scheduler = scheduler or MissionScheduler(self.config)
        self.executive = ExecutiveOrchestrator(
            self.config,
            registry=self.registry,
            planner=self.planner,
            scheduler=self.scheduler,
            runners=self.runners,
            policy=self.policy,
            events=self.events,
            goal_analyzer=goal_analyzer or GoalAnalyzer(engine, self.llm),
            reporter=reporter or ReportBuilder(engine, self.llm),
            memory=self.memory,
            experience=self.experience,
        )

    def _session_factory(self):
        """One AgentSession per runner: every specialist on that runner
        shares its world model, memory and event bus."""
        from ..session import AgentSession
        return AgentSession(self.config.engine, events=self.events,
                            llm=self.llm, memory=self.memory)

    def run_mission(self, mission: Union[Mission, str]) -> MissionResult:
        return self.executive.run_mission(mission)
