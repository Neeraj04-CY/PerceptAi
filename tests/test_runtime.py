"""Unit tests for the unified execution loop, using fully faked services."""
from perceptai.contracts import ActionType, HealingPlan, Step, StepStatus, TaskStatus
from perceptai.events import EventType


def _step(action, description="", **params):
    return Step(action=ActionType(action), description=description, params=params)


def test_happy_path_open_and_type(harness):
    session, fakes, events = harness(
        plans=[
            [
                _step("open_app", "open notepad", app="notepad", wait=0.0),
                _step("type", "type hello", text="hello world", app="notepad"),
            ]
        ],
    )
    result = session.run("open notepad and type hello world")

    assert fakes["apps"].opened == ["notepad"]
    assert fakes["actions"].typed == ["hello world"]
    assert result.status == TaskStatus.COMPLETED  # window exists + input target exists
    assert result.verification.verified
    assert len(result.steps) == 2
    assert all(r.ok for r in result.steps)

    types = [e.type for e in events]
    assert types[0] == EventType.TASK_STARTED
    assert EventType.PLAN_CREATED in types
    assert types.count(EventType.STEP_STARTED) >= 2
    assert types[-1] == EventType.TASK_COMPLETED


def test_no_plan_fails_structurally(harness):
    session, fakes, events = harness(plans=[])
    result = session.run("do something impossible")
    assert result.status == TaskStatus.FAILED
    assert result.errors == ["Could not plan task"]
    assert [e.type for e in events][-1] == EventType.TASK_COMPLETED


def test_failure_type_none_on_success(harness):
    session, fakes, events = harness(
        plans=[
            [
                _step("open_app", "open notepad", app="notepad", wait=0.0),
                _step("type", "type hello", text="hello world", app="notepad"),
            ]
        ],
    )
    result = session.run("open notepad and type hello world")
    assert result.status == TaskStatus.COMPLETED
    # A completed run carries no structured failure cause, and it round-trips.
    assert result.failure_type is None
    assert result.to_dict()["failure_type"] is None


def test_failure_type_set_and_persisted_on_failure(harness):
    session, fakes, events = harness(plans=[])
    result = session.run("do something impossible")
    assert result.status == TaskStatus.FAILED
    # An unclassified structural failure still reports a concrete cause,
    # and it is present in the persisted (serialized) result for analytics.
    assert result.failure_type == "unknown"
    assert result.to_dict()["failure_type"] == "unknown"


def test_click_finds_element_via_ocr(harness):
    session, fakes, events = harness(
        plans=[[_step("click", "click submit", find="Submit", app="myapp")]],
        screens=[["Home", "Submit", "Cancel"]],
        windows=["myapp - window"],
    )
    result = session.run("click submit")
    assert len(fakes["actions"].clicks) == 1
    assert result.steps[0].ok


def test_click_missing_element_fails_without_blind_click(harness):
    session, fakes, events = harness(
        plans=[[_step("click", "click ghost", find="Ghost Button", app="myapp")]],
        screens=[["Home", "Other"]],
        windows=["myapp - window"],
        config=None,
    )
    result = session.run("click a button that does not exist")
    # No fallback click happened
    assert fakes["actions"].clicks == []
    assert result.status == TaskStatus.FAILED
    assert "not found" in result.steps[0].error


def test_healing_recovers_failed_step(harness):
    session, fakes, events = harness(
        plans=[[_step("type", "type into app", text="hello", app="notepad")]],
        windows=["notepad - window"],
        healing=[
            HealingPlan(
                diagnosis="window lost focus",
                failure_type="wrong_screen",
                steps=[_step("focus_window", "refocus", window="notepad")],
                confidence=0.9,
            )
        ],
    )
    fakes["actions"].fail_next_type = True
    result = session.run("type hello")

    assert fakes["healer"].calls == 1
    # original failed step is recorded as healed; recovery step appended
    assert result.steps[0].status == StepStatus.HEALED
    assert any(r.step.source == "healer" for r in result.steps)
    assert result.metadata["healings"] >= 1


def test_recovery_settles_before_measuring(harness, monkeypatch):
    """Sprint 5 reliability fix: after a recovery action the runtime settles
    (config-driven) before judging whether the failure cleared — so a
    still-rendering screen never falsely rejects a recovery that worked."""
    from perceptai.simulation import fast_config
    import perceptai.runtime as rt

    slept: list = []
    monkeypatch.setattr(rt.time, "sleep", lambda s: slept.append(s))

    session, fakes, events = harness(
        plans=[[_step("type", "type into app", text="hello", app="notepad")]],
        windows=["notepad - window"],
        healing=[HealingPlan(
            diagnosis="window lost focus", failure_type="focus_lost",
            steps=[_step("focus_window", "refocus", window="notepad")], confidence=0.9,
        )],
        config=fast_config(settle_after_recovery_s=0.5),
    )
    fakes["actions"].fail_next_type = True
    session.run("type hello")

    assert 0.5 in slept  # the post-recovery settle fired, honoring config (not a literal)


def test_unhealed_failure_triggers_replan_then_stops(harness):
    session, fakes, events = harness(
        plans=[
            [_step("open_app", "open app", app="brokenapp")],
            [_step("open_app", "try again differently", app="otherapp")],
        ],
        healing=[HealingPlan(confidence=0.0), HealingPlan(confidence=0.0)],
    )
    fakes["apps"].fail_apps = {"brokenapp"}
    result = session.run("open broken app")

    # replan produced a working alternative
    assert "otherapp" in fakes["apps"].opened
    assert result.metadata["replans"] >= 1


def test_step_budget_is_enforced(harness):
    from tests.conftest import fast_config

    many = [[_step("wait", f"wait {i}", wait=0.0) for i in range(10)] for _ in range(5)]
    session, fakes, events = harness(
        plans=many,
        config=fast_config(max_steps=4),
    )
    result = session.run("wait forever")
    assert len(result.steps) <= 4


def test_read_screen_produces_findings(harness):
    session, fakes, events = harness(
        plans=[[_step("read_screen", "read the price", find="the price", app="shop")]],
        extractions={"the price": "$19.99"},
    )
    result = session.run("find the price")
    assert result.findings
    assert result.findings[0].value == "$19.99"
    assert result.steps[0].data["extracted"] == "$19.99"


def test_placeholder_type_uses_extraction(harness):
    session, fakes, events = harness(
        plans=[
            [
                _step("read_screen", "read headline", find="headline", app="news"),
                _step("type", "type the headline", text="extracted_text", app="notepad"),
            ]
        ],
        windows=["notepad - window", "news - window"],
        extractions={"headline": "Big News Today"},
    )
    session.run("copy the headline into notepad")
    assert fakes["actions"].typed == ["Big News Today"]


def test_launch_triggers_replan_from_fresh_screen(harness):
    session, fakes, events = harness(
        plans=[
            [_step("open_app", "open notepad", app="notepad", wait=0.0)],
            [_step("type", "now type", text="hi", app="notepad")],
        ],
    )
    result = session.run("open notepad and type hi")
    assert fakes["planner"].plan_calls == 2
    assert fakes["actions"].typed == ["hi"]
    assert any(e.type == EventType.REPLANNED for e in events)


def test_memory_hooks_record_interface_and_task(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
        screens=[["File", "Edit", "Help"]],
    )
    session.run("open notepad")
    assert fakes["memory"].tasks, "task pattern was not remembered"
    assert fakes["memory"].interfaces, "interface elements were not remembered"


def test_events_and_result_share_step_data(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    result = session.run("open notepad")
    completed = [e for e in events if e.type == EventType.STEP_COMPLETED]
    assert len(completed) == len(result.steps)
    assert completed[0].payload["step_number"] == result.steps[0].index


def test_world_snapshots_are_emitted_on_canonical_stream(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
        screens=[["File", "Edit"]],
    )
    session.run("open notepad")
    snapshots = [e for e in events if e.type == EventType.WORLD_SNAPSHOT]
    assert snapshots, "planning must emit a world snapshot"
    payload = snapshots[0].payload
    assert "confidence" in payload
    assert "providers" in payload
    assert any(p["name"] == "ocr" for p in payload["providers"])


def test_click_outcome_carries_perception_confidence(harness):
    session, fakes, events = harness(
        plans=[[_step("click", "click submit", find="Submit", app="myapp")]],
        screens=[["Home", "Submit", "Cancel"]],
        windows=["myapp - window"],
    )
    result = session.run("click submit")
    data = result.steps[0].data
    assert data["element"] == "Submit"
    assert 0.0 < data["confidence"] <= 0.99
    assert "ocr" in data["sources"]
