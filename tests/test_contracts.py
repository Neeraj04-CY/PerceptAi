import json

from perceptai.contracts import (
    ActionType,
    Finding,
    Step,
    StepResult,
    StepStatus,
    Task,
    TaskContext,
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
        steps=[StepResult(step=step, status=StepStatus.COMPLETED, index=1)],
        findings=[Finding(label="x", value="y")],
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


def test_task_context_extractions():
    ctx = TaskContext(instruction="find price")
    assert ctx.latest_extraction == ""
    ctx.add_extraction("price", "$42", source="step 2")
    ctx.add_extraction("name", "Acme", source="step 3")
    assert ctx.latest_extraction == "Acme"
    assert ctx.facts["price"] == "$42"
    assert len(ctx.extractions) == 2


def test_task_gets_unique_ids():
    assert Task(instruction="a").id != Task(instruction="a").id
