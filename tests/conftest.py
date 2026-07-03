"""Shared fakes for engine unit tests. No LLM calls, no screen control."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from perceptai.config import EngineConfig
from perceptai.contracts import ActionOutcome, HealingPlan, PlannerOutput, Step
from perceptai.events import EventBus
from perceptai.perception import Perception, TextBlock
from perceptai.session import AgentSession


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

    def perceive_full(self, region=None) -> Perception:
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

    def open(self, app):
        if app in self.fail_apps:
            return ActionOutcome(ok=False, error=f"cannot launch {app}")
        self.opened.append(app)
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
    """Returns queued PlannerOutputs; empty output when exhausted."""

    def __init__(self, plans: list[list[Step]] | None = None, extractions: dict[str, str] | None = None):
        self.plans = list(plans or [])
        self.extractions = extractions or {}
        self.plan_calls = 0

    def plan(self, instruction, screen_text, completed, open_windows=None, source="planner"):
        self.plan_calls += 1
        if self.plans:
            return PlannerOutput(steps=self.plans.pop(0))
        return PlannerOutput(ok=False, error="no more plans")

    def extract(self, goal, screen_text):
        return self.extractions.get(goal, "")


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
    def __init__(self):
        self.interfaces: list[tuple[str, list]] = []
        self.tasks: list[tuple] = []

    def remember_interface(self, app, elements):
        self.interfaces.append((app, elements))

    def recall_element(self, app, text):
        return None

    def remember_task(self, instruction, steps, success, execution_time):
        self.tasks.append((instruction, steps, success, execution_time))

    def recall_task(self, instruction):
        return None


class FakeLLM:
    calls = 0


def fast_config(**overrides) -> EngineConfig:
    defaults = dict(
        groq_api_key="test",
        settle_after_launch_s=0.0,
        settle_after_step_s=0.0,
        settle_before_input_s=0.0,
        fast_cache_ttl_s=0.0,
    )
    defaults.update(overrides)
    return EngineConfig(**defaults)


@pytest.fixture
def harness(tmp_path):
    """A fully faked AgentSession plus handles to every fake."""

    def build(plans=None, screens=None, windows=None, healing=None, extractions=None, config=None):
        cfg = config or fast_config(workspace_root=tmp_path)
        fake_windows = FakeWindows(windows)
        fakes = {
            "windows": fake_windows,
            "perception": FakePerception(screens),
            "apps": FakeApps(fake_windows),
            "actions": FakeActions(),
            "planner": FakePlanner(plans, extractions),
            "healer": FakeHealer(healing),
            "memory": FakeMemory(),
        }
        events: list = []
        bus = EventBus()
        bus.subscribe(events.append)
        session = AgentSession(
            cfg,
            events=bus,
            llm=FakeLLM(),
            **fakes,
        )
        # Verifier is real (pure logic) and uses the fake WindowManager.
        return session, fakes, events

    return build
