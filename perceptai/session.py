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
from .constraints import ConstraintManager
from .contracts import Task, TaskResult, TaskStatus
from .critic import PlanCritic
from .control import ControlChannel
from .egress import TEXT, EgressGuard
from .events import EventBus, EventType
from .risk import RiskAssessor
from .secrets import NullSecretResolver, SecretResolver
from .evidence import EvidenceCollector
from .goal import GoalAnalyzer
from .healer import Healer
from .hypothesis import HypothesisGenerator
from .llm import LLMClient
from .memory import MemoryStore
from .oscontrol import AppLauncher, WindowManager
from .perception import PerceptionService
from .planner import Planner
from .providers import default_providers
from .reasoning import ReasoningEngine
from .recovery import RecoveryManager
from .reporting import ReportBuilder
from .verification import Verifier
from .world import WorldModel


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
        goal_analyzer: Optional[GoalAnalyzer] = None,
        evidence_collector: Optional[EvidenceCollector] = None,
        reporter: Optional[ReportBuilder] = None,
        world: Optional[WorldModel] = None,
        reasoning: Optional[ReasoningEngine] = None,
        recovery: Optional[RecoveryManager] = None,
        constraints: Optional[ConstraintManager] = None,
        control: Optional[ControlChannel] = None,
        risk: Optional[RiskAssessor] = None,
        critic: Optional[PlanCritic] = None,
        secrets: Optional[SecretResolver] = None,
        egress: Optional[EgressGuard] = None,
    ):
        self.config = config or EngineConfig.from_env()
        self.id = str(uuid.uuid4())
        self.workspace = self.config.workspace_root / self.id[:8]

        self.events = events or EventBus()
        # Data-egress policy: injected, workspace-owned, enforced at the ONE
        # LLM checkpoint. Defaults to allow-all so local dev and tests are
        # unchanged; the API/runner inject the workspace's policy.
        self.egress = egress or EgressGuard()
        self.llm = llm or LLMClient(self.config, egress=self.egress)
        self.windows = windows or WindowManager()
        self.perception = perception or PerceptionService(self.config, self.llm, self.workspace)
        self.apps = apps or AppLauncher(self.config, self.windows)
        self.actions = actions or ActionExecutor(self.config)
        self.planner = planner or Planner(self.config, self.llm)
        self.healer = healer or Healer(self.config, self.llm)
        self.verifier = verifier or Verifier(self.windows, self.llm, self.config)
        self.memory = memory or MemoryStore(self.config.memory_db_path)
        self.goals = goal_analyzer or GoalAnalyzer(self.config, self.llm)
        self.evidence = evidence_collector or EvidenceCollector(self.config, self.llm)
        self.reporter = reporter or ReportBuilder(self.config, self.llm)
        # The unified perception surface: providers -> fusion -> WorldState.
        # Built last so injected fakes (perception, windows, llm) flow into
        # the default provider set automatically.
        self.world = world or WorldModel(
            self.config,
            default_providers(
                self.config, perception=self.perception,
                windows=self.windows, llm=self.llm,
            ),
        )
        # The reasoning layer: stateless services; per-run state lives in
        # the ReasoningState the engine creates for each task.
        self.reasoning = reasoning or ReasoningEngine(self.config)
        self.recovery = recovery or RecoveryManager(
            self.config, self.healer, HypothesisGenerator(self.config)
        )
        self.constraints = constraints or ConstraintManager(self.config)
        # Trust layer: control is the interruptibility surface (pass-through
        # unless a controller attaches); risk is the deterministic "what could
        # go wrong" signal read before every input action.
        self.control = control or ControlChannel()
        self.risk = risk or RiskAssessor(self.config)
        # The Plan Critic (Chapter XVI): an adversarial second role that
        # attacks each plan BEFORE it runs. Verification moves ahead of the
        # action, so a wrong click is prevented rather than detected.
        self.critic = critic or PlanCritic(
            self.config, llm=self.llm, risk=self.risk, world=self.world)
        # Secret resolution is out-of-band and per-run: the default resolves
        # nothing; the API/runner inject a workspace-scoped, zeroizing resolver.
        self.secrets = secrets or NullSecretResolver()
        # An injected LLM (tests, fakes) must still honor workspace egress
        # policy — the checkpoint belongs to the session, not to one client.
        if egress is not None and hasattr(self.llm, "egress"):
            self.llm.egress = self.egress

    def emit(self, type: EventType, task: Task, **payload) -> None:
        self.events.emit(type, session_id=self.id, task_id=task.id, **payload)

    def run(self, task: Union[Task, str]) -> TaskResult:
        """Execute one task to completion and return its structured result."""
        from .runtime import ExecutionEngine

        if isinstance(task, str):
            task = Task(instruction=task)

        # Egress policy 'deny' means no observation may reach any model, and
        # the engine plans from observations. Refuse UP FRONT with a named
        # reason rather than contacting a model, half-executing, and failing
        # obscurely. The platform never pretends work can proceed when it cannot.
        if not self.egress.allows_text:
            return TaskResult(
                task_id=task.id, instruction=task.instruction,
                status=TaskStatus.FAILED,
                summary="Refused before execution: workspace data-egress policy "
                        "denies sending screen observations to any model.",
                errors=[self.egress.policy.reason(TEXT)],
                confidence=1.0,
            )
        try:
            return ExecutionEngine(self).run(task)
        finally:
            # Secret lifetime invariant: zeroize and drop any resolved secret
            # values the instant the run ends — success, failure, or abort.
            try:
                self.secrets.purge()
            except Exception:
                pass
