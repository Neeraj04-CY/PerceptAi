"""Runtime integration of the cognitive layer (goal, evidence, report, memory)."""
from perceptai.contracts import ActionType, GoalSpec, Step, TaskStatus
from perceptai.events import EventType
from tests.conftest import FakeMemory, ScriptedGoalAnalyzer


def _step(action, description="", **params):
    return Step(action=ActionType(action), description=description, params=params)


def test_goal_analyzed_event_emitted_before_planning(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.run("open notepad")
    types = [e.type for e in events]
    assert EventType.GOAL_ANALYZED in types
    assert types.index(EventType.GOAL_ANALYZED) < types.index(EventType.PLAN_CREATED)


def test_result_carries_goal_and_report(harness):
    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    result = session.run("open notepad")
    assert result.goal is not None
    assert result.goal.intent == "open notepad"  # fallback goal from FakeLLM failure
    assert result.report is not None
    assert result.report.executive_summary  # template fallback is non-empty
    assert result.summary == result.report.executive_summary


def test_evidence_flows_to_findings_report_and_memory(harness):
    memory = FakeMemory()
    session, fakes, events = harness(
        plans=[[_step("read_screen", "read the price", find="the price", app="shop")]],
        extractions={"the price": "$19.99"},
        memory=memory,
    )
    result = session.run("find the price")
    assert result.findings[0].value == "$19.99"
    assert result.findings[0].kind == "text"
    assert result.report.evidence[0].value == "$19.99"
    assert memory.evidence, "evidence was not persisted to the knowledge store"
    assert any(e.type == EventType.EVIDENCE_COLLECTED for e in events)


def test_recalled_knowledge_seeds_working_memory(harness):
    memory = FakeMemory(knowledge=[
        {"entity": "Acme", "attribute": "price", "value": "$5", "source": "old-task",
         "confidence": 0.9, "created_at": 0},
    ])
    goal = GoalSpec(intent="research Acme", entities=["Acme"], objectives=["research Acme"])
    session, fakes, events = harness(
        plans=[[_step("open_app", "open browser", app="notepad", wait=0.0)]],
        goal_analyzer=ScriptedGoalAnalyzer(goal),
        memory=memory,
    )
    result = session.run("research Acme")
    # recalled fact landed in working memory and is noted
    goal_events = [e for e in events if e.type == EventType.GOAL_ANALYZED]
    assert goal_events[0].payload["recalled_facts"] == 1


def test_sources_are_tracked(harness):
    session, fakes, events = harness(
        plans=[
            [
                _step("open_app", "open notepad", app="notepad", wait=0.0),
                _step("navigate_url", "visit example", url="https://example.com", wait=0.0),
            ]
        ],
    )
    result = session.run("open notepad and visit example.com")
    assert "notepad" in result.metadata["sources"]
    assert "https://example.com" in result.metadata["sources"]
    assert result.report.sources == result.metadata["sources"]


def test_goal_driven_continuation_until_planner_says_done(harness):
    goal = GoalSpec(
        intent="collect the price",
        output_format="data",
        objectives=["collect the price"],
        completion_criteria=["price collected"],
    )
    session, fakes, events = harness(
        plans=[
            [_step("read_screen", "read price", find="the price", app="shop")],
            # continuation replan: planner still has work
            [_step("read_screen", "read second price", find="other price", app="shop")],
            # next continuation: planner exhausted -> not ok -> loop ends
        ],
        extractions={"the price": "$1", "other price": "$2"},
        goal_analyzer=ScriptedGoalAnalyzer(goal),
    )
    result = session.run("collect the price")
    assert len(result.findings) == 2  # continuation executed the second batch
    assert fakes["planner"].plan_calls == 3
    assert result.metadata["replans"] >= 1


def test_no_continuation_without_completion_criteria(harness):
    session, fakes, events = harness(
        plans=[
            [_step("open_app", "open notepad", app="notepad", wait=0.0)],
            [_step("type", "type hi", text="hi", app="notepad")],
        ],
    )
    session.run("open notepad and type hi")
    # initial plan + post-launch replan only; no continuation calls after queue empties
    assert fakes["planner"].plan_calls == 2


def test_complete_sse_carries_summary_and_report(harness):
    from perceptai.streaming import to_legacy_sse

    session, fakes, events = harness(
        plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
    )
    session.run("open notepad")
    completed = next(e for e in events if e.type == EventType.TASK_COMPLETED)
    sse = to_legacy_sse(completed)
    assert sse["type"] == "complete"
    assert sse["summary"]
    assert sse["report"]["executive_summary"]
