"""Integration: the decision-driven loop, reasoning events, honest recovery."""
from perceptai.contracts import (
    ActionType,
    GoalSpec,
    HealingPlan,
    Step,
    StepStatus,
    TaskStatus,
)
from perceptai.events import EventType
from perceptai.streaming import to_legacy_sse

from tests.conftest import ScriptedGoalAnalyzer, fast_config


def _step(action, description="", **params):
    return Step(action=ActionType(action), description=description, params=params)


def _events_of(events, type_):
    return [e for e in events if e.type == type_]


def test_every_cycle_emits_an_explained_decision(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.run("open notepad")
    decisions = _events_of(events, EventType.DECISION_MADE)
    assert decisions, "the loop must emit decisions"
    for event in decisions:
        assert event.payload["decision"]
        assert event.payload["reason"]
        assert "uncertainty" in event.payload["factors"]
        assert "budget" in event.payload
    # the run terminates on an explicit decision, not a fall-through
    assert decisions[-1].payload["decision"] in ("finish", "abort", "need_user")


def test_strategy_selected_and_fed_to_planner(harness):
    goal = GoalSpec(intent="research prices", output_format="report",
                    objectives=["find prices"])
    session, fakes, events = harness(
        plans=[[_step("read_screen", "read prices", find="prices", app="shop")]],
        extractions={"prices": "$5"},
        goal_analyzer=ScriptedGoalAnalyzer(goal),
    )
    session.run("research prices")
    selected = _events_of(events, EventType.STRATEGY_SELECTED)
    assert len(selected) == 1
    assert selected[0].payload["strategy"] == "research"
    assert "research" in fakes["planner"].strategies_seen


def test_actions_seed_beliefs_and_world_corroborates(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    result = session.run("open notepad")
    beliefs = _events_of(events, EventType.BELIEF_UPDATED)
    notepad = [e for e in beliefs if e.payload.get("subject") == "notepad"]
    assert notepad, "open_app must seed a window_open belief"
    assert notepad[0].payload["confidence"] == 0.7  # action alone is not certainty
    # a later observation corroborated it (FakeApps registered the window)
    assert any(e.payload["confidence"] > 0.7 for e in notepad[1:])
    summary = result.metadata["reasoning"]
    assert any(b["kind"] == "window_open" for b in summary["beliefs"])


def test_false_recovery_is_rejected_and_task_fails_honestly(harness):
    """A wait-based 'loading' recovery runs fine but cannot conjure the
    missing element: the hypothesis must be rejected and the task FAILED."""
    session, fakes, events = harness(
        plans=[[_step("click", "click ghost", find="Ghost Button", app="myapp")]],
        screens=[["Home", "Other"]],
        windows=["myapp - window"],
    )
    result = session.run("click a button that does not exist")

    assert fakes["actions"].clicks == []
    assert result.status == TaskStatus.FAILED

    resolved = _events_of(events, EventType.HYPOTHESIS_RESOLVED)
    rejected = [e for e in resolved if e.payload["status"] == "rejected"]
    assert rejected, "the false recovery must reject its hypothesis"
    completions = _events_of(events, EventType.RECOVERY_COMPLETED)
    assert completions and not any(e.payload["recovered"] for e in completions)


def test_recovery_confirms_hypothesis_when_condition_clears(harness):
    session, fakes, events = harness(
        plans=[[_step("type", "type into app", text="hello", app="notepad")]],
        windows=["notepad - window"],
        healing=[HealingPlan(diagnosis="window lost focus", failure_type="focus_lost",
                             steps=[_step("focus_window", "refocus", window="notepad")],
                             confidence=0.9)],
    )
    fakes["actions"].fail_next_type = True
    result = session.run("type hello")

    assert result.steps[0].status == StepStatus.HEALED
    created = _events_of(events, EventType.HYPOTHESIS_CREATED)
    assert any(e.payload["kind"] == "focus_lost" for e in created)
    resolved = _events_of(events, EventType.HYPOTHESIS_RESOLVED)
    assert any(e.payload["status"] == "confirmed" for e in resolved)
    assert result.metadata["reasoning"]["hypotheses"]["confirmed"] >= 1


def test_replanned_around_failure_lets_verification_own_the_verdict(harness):
    session, fakes, events = harness(
        plans=[
            [_step("open_app", "open app", app="brokenapp")],
            [_step("open_app", "try another app", app="otherapp")],
        ],
        healing=[HealingPlan(confidence=0.0), HealingPlan(confidence=0.0)],
    )
    fakes["apps"].fail_apps = {"brokenapp"}
    result = session.run("open an editor")

    assert "otherapp" in fakes["apps"].opened
    failed_step = result.steps[0]
    assert failed_step.status == StepStatus.SKIPPED  # superseded, preserved
    assert failed_step.error
    # the alternate path succeeded and verification confirmed it
    assert result.status in (TaskStatus.COMPLETED, TaskStatus.UNVERIFIED)
    assert result.status != TaskStatus.FAILED


def test_blocked_window_policy_denies_input_and_replans(harness):
    config = fast_config(blocked_window_titles=["myapp"])
    session, fakes, events = harness(
        plans=[
            [_step("type", "type into blocked app", text="hi", app="myapp")],
            [_step("read_screen", "observe instead", find="content", app="myapp")],
        ],
        windows=["myapp - window"],
        screens=[["content here"]],
        extractions={"content": "the content"},
        config=config,
    )
    result = session.run("get the content")

    assert fakes["actions"].typed == []  # policy held
    denied = result.steps[0]
    assert "constraint" in denied.error
    decisions = [e.payload["decision"] for e in _events_of(events, EventType.DECISION_MADE)]
    assert "recover" not in decisions, "policy denials are replanned, not healed"
    assert "replan" in decisions


def test_changing_ui_failure_recovers_through_replanning(harness):
    """The planned button disappears before the click: recovery cannot fix
    it, the replan from the live screen finds the renamed control."""
    session, fakes, events = harness(
        plans=[
            [_step("click", "click Submit", find="Submit", app="myapp")],
            [_step("click", "click Submit Form", find="Submit Form", app="myapp")],
        ],
        screens=[["Welcome", "Submit Form", "Cancel", "Header", "Footer"]],
        windows=["myapp - window"],
    )
    result = session.run("submit the form")
    assert len(fakes["actions"].clicks) == 1  # the replanned click landed
    assert result.steps[-1].ok


def test_reasoning_summary_is_replayable(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    result = session.run("open notepad")
    summary = result.metadata["reasoning"]
    assert summary["strategy"]
    assert summary["cycles"] >= 2
    assert summary["decisions"].get("continue", 0) >= 1
    assert summary["trajectory"], "every cycle must be replayable"
    for record in summary["trajectory"]:
        assert record["decision"] and record["reason"]
    assert summary["confidence_history"]


def test_reasoning_events_map_to_additive_sse(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.run("open notepad")
    reasoning_types = {
        EventType.STRATEGY_SELECTED, EventType.DECISION_MADE, EventType.BELIEF_UPDATED,
    }
    mapped = [to_legacy_sse(e) for e in events if e.type in reasoning_types]
    assert mapped
    for sse in mapped:
        assert sse["type"] == "reasoning"
        assert sse["kind"]
        assert sse["timestamp"]


def test_cycle_budget_bounds_the_loop(harness):
    config = fast_config(max_cycles=3)
    many = [[_step("wait", f"wait {i}", wait=0.0) for i in range(5)] for _ in range(3)]
    session, fakes, events = harness(plans=many, config=config)
    result = session.run("wait around")
    assert result.metadata["reasoning"]["cycles"] <= 3
