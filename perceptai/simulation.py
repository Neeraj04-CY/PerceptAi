"""Deterministic in-memory service fakes — the simulation substrate.

One source of truth for every scripted stand-in used by unit tests
(tests/conftest.py) and offline evaluation (evals/reasoning_bench.py).
No LLM calls, no screen control, no network: a simulated session runs
the REAL runtime, world model, fusion and reasoning engine against
scriptable perception and actions, so reasoning quality is measurable
in CI and on headless hosts.
"""
from __future__ import annotations

from .config import EngineConfig
from .contracts import ActionOutcome, Evidence, HealingPlan, PlannerOutput, Step
from .perception import Perception, TextBlock


class FakePerception:
    """Scriptable perception: pops screens from a queue, repeats the last one."""

    def __init__(self, screens: list[list[str]] | None = None):
        self.screens = screens or [["Desktop"]]
        self.calls = 0
        self.latest_screenshot = None

    def _next(self) -> Perception:
        idx = min(self.calls, len(self.screens) - 1)
        self.calls += 1
        blocks = [
            TextBlock(text=t, confidence=0.9, x=100 + 10 * i, y=200 + 10 * i)
            for i, t in enumerate(self.screens[idx])
        ]
        return Perception(text_blocks=blocks, mode="fast")

    def perceive_fast(self, region=None, force_refresh=False) -> Perception:
        return self._next()


class FakeWindows:
    def __init__(self, windows: list[str] | None = None):
        self.windows = windows if windows is not None else []
        self.focus_calls: list[str] = []

    def list_windows(self):
        return list(self.windows)

    def exists(self, keyword):
        k = keyword.lower()
        return next((w for w in self.windows if k in w.lower()), None)

    def focus(self, keyword):
        self.focus_calls.append(keyword)
        if self.exists(keyword):
            return ActionOutcome(ok=True, data={"window": keyword})
        return ActionOutcome(ok=False, error=f"Window '{keyword}' not found")


class FakeApps:
    def __init__(self, windows: FakeWindows):
        self._windows = windows
        self.opened: list[str] = []
        self.navigated: list[str] = []
        self.fail_apps: set[str] = set()
        # Apps that report a successful launch but never produce a window —
        # the "false action success" failure mode.
        self.silent_apps: set[str] = set()

    def open(self, app):
        if app in self.fail_apps:
            return ActionOutcome(ok=False, error=f"cannot launch {app}")
        self.opened.append(app)
        if app not in self.silent_apps:
            self._windows.windows.append(f"{app} - window")
        return ActionOutcome(ok=True, data={"app": app})

    def navigate(self, url):
        self.navigated.append(url)
        return ActionOutcome(ok=True, data={"url": url, "browser": "default"})


class FakeActions:
    def __init__(self):
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []
        self.pressed: list[str] = []
        self.fail_next_type = False

    def click(self, x, y, double=False):
        self.clicks.append((x, y))
        return ActionOutcome(ok=True, data={"x": x, "y": y})

    def type_text(self, text):
        if self.fail_next_type:
            self.fail_next_type = False
            return ActionOutcome(ok=False, error="type failed")
        self.typed.append(text)
        return ActionOutcome(ok=True, data={"text": text})

    def clear_and_type(self, text):
        return self.type_text(text)

    def press(self, key):
        self.pressed.append(key)
        return ActionOutcome(ok=True, data={"key": key})

    def scroll(self, x, y, direction="down", amount=3):
        return ActionOutcome(ok=True, data={"direction": direction})

    def screen_size(self):
        return 1920, 1080


class FakePlanner:
    """Returns queued PlannerOutputs; not-ok output when exhausted.
    A scripted empty plan ([]) is the planner's 'goal achieved' signal."""

    def __init__(self, plans: list[list[Step]] | None = None):
        self.plans = list(plans or [])
        self.plan_calls = 0
        self.strategies_seen: list[str] = []

    def plan(self, instruction, screen_text, completed, open_windows=None,
             source="planner", goal=None, known_facts=None, strategy=None,
             available_secrets=None):
        self.plan_calls += 1
        if strategy is not None:
            self.strategies_seen.append(strategy.name)
        if self.plans:
            return PlannerOutput(steps=self.plans.pop(0))
        return PlannerOutput(ok=False, error="no more plans")


class FakeEvidenceCollector:
    """Returns scripted evidence per goal_info string."""

    def __init__(self, extractions: dict[str, str] | None = None):
        self.extractions = extractions or {}
        self.calls: list[tuple[str, str]] = []

    def collect(self, goal_info, screen_text, source):
        self.calls.append((goal_info, source))
        value = self.extractions.get(goal_info, "")
        if not value:
            return []
        return [Evidence(kind="text", label=goal_info, value=value, source=source, confidence=0.9)]


class FakeHealer:
    def __init__(self, plans: list[HealingPlan] | None = None):
        self.plans = list(plans or [])
        self.calls = 0

    def diagnose(self, failed_step, error_info, screen_text):
        self.calls += 1
        if self.plans:
            return self.plans.pop(0)
        return HealingPlan(diagnosis="unknown", confidence=0.0)


class FakeMemory:
    def __init__(self, knowledge: list[dict] | None = None):
        self.interfaces: list[tuple[str, list]] = []
        self.tasks: list[tuple] = []
        self.evidence: list[tuple[str, list]] = []
        self.knowledge = knowledge or []

    def remember_interface(self, app, elements):
        self.interfaces.append((app, elements))

    def recall_element(self, app, text):
        return None

    def remember_task(self, instruction, steps, success, execution_time):
        self.tasks.append((instruction, steps, success, execution_time))

    def recall_task(self, instruction):
        return None

    def remember_evidence(self, task_id, evidence):
        self.evidence.append((task_id, list(evidence)))

    def recall_knowledge(self, terms, limit=10):
        return list(self.knowledge)


class FakeLLM:
    calls = 0


class ScriptedGoalAnalyzer:
    """Inject to give the runtime a rich GoalSpec."""

    def __init__(self, spec):
        self.spec = spec

    def analyze(self, instruction, known_facts=""):
        return self.spec


def fast_config(**overrides) -> EngineConfig:
    """Engine config for simulation: zero settle delays, hermetic providers.
    The UIA provider is disabled because it would otherwise observe the
    REAL desktop (read-only, but nondeterministic) during simulated runs."""
    defaults = dict(
        groq_api_key="test",
        settle_after_launch_s=0.0,
        settle_after_step_s=0.0,
        settle_before_input_s=0.0,
        settle_before_read_s=0.0,
        find_retry_wait_s=0.0,
        recovery_retry_wait_s=0.0,
        settle_after_recovery_s=0.0,
        fast_cache_ttl_s=0.0,
        uia_enabled=False,
        dom_enabled=False,   # never attach to a real browser during simulation
    )
    defaults.update(overrides)
    return EngineConfig(**defaults)


# ------------------------------------------------------------- workforce

class FakeSpecialist:
    """Scriptable deterministic execution unit for workforce tests.

    `script` maps an objective substring to a dict describing the result:
    {"outputs": {...}, "evidence": [(label, value, source, confidence)],
     "fail": bool, "error": str, "latency_s": float}. Unscripted
    objectives succeed with a generic result."""

    def __init__(self, name: str, capabilities: list[str],
                 script: dict | None = None, resources: list[str] | None = None,
                 cost: float = 1.0, confidence: float = 0.8,
                 fail_all: bool = False, latency_s: float = 0.0,
                 max_concurrent: int = 1):
        from .workforce.contracts import SpecialistProfile
        self.profile = SpecialistProfile(
            name=name, capabilities=list(capabilities), cost=cost,
            confidence=confidence, resources=list(resources or []),
            max_concurrent=max_concurrent, provider="fake",
        )
        self.script = script or {}
        self.fail_all = fail_all
        self.latency_s = latency_s
        self.executed: list = []  # WorkOrder objects, in execution order

    def healthy(self) -> bool:
        return True

    def execute(self, order, ctx):
        import time as _time

        from .contracts import Evidence as _Evidence
        from .workforce.contracts import WorkResult, WorkStatus
        self.executed.append(order)
        spec = next((v for k, v in self.script.items()
                     if k.lower() in order.objective.lower()), {})
        latency = float(spec.get("latency_s", self.latency_s))
        if latency:
            _time.sleep(latency)
        if self.fail_all or spec.get("fail"):
            return WorkResult(
                order_id=order.id, specialist=self.profile.name,
                status=WorkStatus.FAILED,
                error=str(spec.get("error", "scripted failure")),
                duration_s=latency, cost=self.profile.cost,
            )
        evidence = [
            _Evidence(kind="text", label=label, value=value,
                      source=source, confidence=conf)
            for (label, value, source, conf) in spec.get("evidence", [])
        ]
        outputs = dict(spec.get("outputs", {}))
        for key in order.produces:
            outputs.setdefault(key, f"{key} from {self.profile.name}")
        return WorkResult(
            order_id=order.id, specialist=self.profile.name,
            status=WorkStatus.COMPLETED,
            summary=str(spec.get("summary", f"{order.objective} done")),
            outputs=outputs, evidence=evidence,
            confidence=float(spec.get("confidence", self.profile.confidence)),
            duration_s=latency, cost=self.profile.cost,
        )


class ScriptedMissionPlanner:
    """Returns the given work orders — decomposition without an LLM."""

    def __init__(self, orders: list):
        self._orders = orders
        self.calls = 0

    def decompose(self, instruction, goal, capabilities, known_facts=None):
        import copy
        self.calls += 1
        return copy.deepcopy(self._orders)


def build_simulated_workforce(
    orders, specialists, config=None, policy=None, memory=None,
    experience=None, goal=None,
):
    """A fully simulated Workforce plus the captured canonical event
    stream. FakeSpecialists never touch a session; the runner pool's
    factory exists only so desktop-resource leases have something to
    hand out."""
    from .events import EventBus
    from .workforce import (
        MissionPolicy,
        MissionScheduler,
        RunnerPool,
        SpecialistRegistry,
        Workforce,
        WorkforceConfig,
    )

    cfg = config or WorkforceConfig(engine=fast_config(), wait_poll_s=0.01)
    if experience is None:
        # Hermetic by default: experience must never touch the real
        # ~/.perceptai database from a simulated run.
        import tempfile as _tempfile
        from pathlib import Path as _Path

        from .workforce import ExperienceStore
        experience = ExperienceStore(
            _Path(_tempfile.mkdtemp(prefix="perceptai-sim-")) / "experience.db")
    registry = SpecialistRegistry()
    for specialist in specialists:
        registry.register(specialist)
    events: list = []
    bus = EventBus()
    bus.subscribe(events.append)
    workforce = Workforce(
        cfg,
        events=bus,
        llm=FakeLLM(),
        registry=registry,
        runners=RunnerPool(lambda: None),
        planner=ScriptedMissionPlanner(orders),
        scheduler=MissionScheduler(cfg),
        policy=policy or MissionPolicy(),
        memory=memory or FakeMemory(),
        experience=experience,
        goal_analyzer=ScriptedGoalAnalyzer(goal) if goal is not None else None,
        discover_plugins=False,
    )
    return workforce, events


def build_simulated_session(
    plans=None, screens=None, windows=None, healing=None, extractions=None,
    config=None, goal_analyzer=None, memory=None, workspace=None,
):
    """A fully simulated AgentSession plus handles to every fake and the
    captured canonical event stream. GoalAnalyzer and ReportBuilder run
    REAL against FakeLLM — their LLM calls fail, exercising the
    degrade-gracefully paths (minimal goal, template report)."""
    from .events import EventBus
    from .session import AgentSession

    cfg = config or fast_config(**({"workspace_root": workspace} if workspace else {}))
    fake_windows = FakeWindows(windows)
    fakes = {
        "windows": fake_windows,
        "perception": FakePerception(screens),
        "apps": FakeApps(fake_windows),
        "actions": FakeActions(),
        "planner": FakePlanner(plans),
        "healer": FakeHealer(healing),
        "memory": memory or FakeMemory(),
        "evidence_collector": FakeEvidenceCollector(extractions),
    }
    events: list = []
    bus = EventBus()
    bus.subscribe(events.append)
    session = AgentSession(
        cfg, events=bus, llm=FakeLLM(), goal_analyzer=goal_analyzer, **fakes,
    )
    return session, fakes, events
