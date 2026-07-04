"""Shared fakes for engine unit tests. No LLM calls, no screen control.

The fake classes live in perceptai.simulation (one source of truth,
shared with evals/reasoning_bench.py); this module re-exports them and
provides the pytest fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from perceptai.simulation import (  # noqa: F401  (re-exported for test modules)
    FakeActions,
    FakeApps,
    FakeEvidenceCollector,
    FakeHealer,
    FakeLLM,
    FakeMemory,
    FakePerception,
    FakePlanner,
    FakeWindows,
    ScriptedGoalAnalyzer,
    build_simulated_session,
    fast_config,
)


@pytest.fixture
def harness(tmp_path):
    """A fully faked AgentSession plus handles to every fake.

    GoalAnalyzer and ReportBuilder are REAL instances running against FakeLLM
    — their LLM calls fail, exercising the degrade-gracefully paths (minimal
    goal, template report). Inject `goal_analyzer=` to script rich goals.
    """

    def build(plans=None, screens=None, windows=None, healing=None,
              extractions=None, config=None, goal_analyzer=None, memory=None):
        return build_simulated_session(
            plans=plans, screens=screens, windows=windows, healing=healing,
            extractions=extractions, config=config, goal_analyzer=goal_analyzer,
            memory=memory, workspace=tmp_path,
        )

    return build
