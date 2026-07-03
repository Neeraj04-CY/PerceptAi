import json

from perceptai.contracts import (
    ActionType,
    Evidence,
    GoalSpec,
    Step,
    StepResult,
    StepStatus,
    Task,
    TaskContext,
    TaskReport,
    TaskResult,
    TaskStatus,
    VerificationCheck,
    VerificationResult,
)


def test_step_from_planner_dict_valid():
    step = Step.from_planner_dict(
        {"action": "click", "description": "click ok", "find": "OK", "wait": 1.0, "app": "notepad"}
    )
    assert step is not None
    assert step.action == ActionType.CLICK
    assert step.params == {"find": "OK", "wait": 1.0, "app": "notepad"}


def test_step_from_planner_dict_unknown_action():
    assert Step.from_planner_dict({"action": "teleport", "description": "??"}) is None


def test_step_from_planner_dict_drops_empty_params():
    step = Step.from_planner_dict({"action": "type", "text": "hi", "url": "", "key": None})
    assert step.params == {"text": "hi"}


def test_task_result_serializes_to_json():
    step = Step(action=ActionType.OPEN_APP, description="open", params={"app": "notepad"})
    result = TaskResult(
        task_id="t1",
        instruction="do it",
        status=TaskStatus.COMPLETED,
        goal=GoalSpec(intent="do it", output_format="data"),
        report=TaskReport(executive_summary="did it", key_findings=["x is y"]),
        steps=[StepResult(step=step, status=StepStatus.COMPLETED, index=1)],
        findings=[Evidence(kind="text", label="x", value="y")],
        verification=VerificationResult(
            verified=True, confidence=1.0, checks=[VerificationCheck(name="c", passed=True)]
        ),
    )
    payload = result.to_dict()
    encoded = json.dumps(payload)  # must be JSON-safe
    decoded = json.loads(encoded)
    assert decoded["status"] == "completed"
    assert decoded["steps"][0]["step"]["action"] == "open_app"
    assert decoded["verification"]["checks"][0]["passed"] is True
    assert decoded["report"]["executive_summary"] == "did it"
    assert decoded["goal"]["output_format"] == "data"


def test_task_context_accumulates_evidence():
    ctx = TaskContext(instruction="find price")
    assert ctx.latest_extraction == ""
    ctx.add_evidence([Evidence(kind="price", label="price", value="$42", source="shop")])
    ctx.add_evidence([Evidence(kind="name", label="name", value="Acme", source="shop")])
    assert ctx.latest_extraction == "Acme"
    assert ctx.facts["price"] == "$42"
    assert len(ctx.evidence) == 2


def test_task_context_sources_dedupe_and_accumulate():
    ctx = TaskContext(instruction="x")
    ctx.add_source("example.com")
    ctx.add_source("example.com")
    ctx.add_source("notepad")
    assert ctx.sources == ["example.com", "notepad"]


def test_goal_spec_information_goal():
    assert GoalSpec(intent="x", output_format="report").is_information_goal
    assert GoalSpec(intent="x", output_format="data").is_information_goal
    assert not GoalSpec(intent="x", output_format="action_confirmation").is_information_goal


def test_task_gets_unique_ids():
    assert Task(instruction="a").id != Task(instruction="a").id
