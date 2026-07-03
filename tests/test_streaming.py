"""The legacy SSE wire format is a consumer contract — the dashboard
depends on these exact shapes. These tests pin them."""
from perceptai.contracts import (
    ActionType,
    Step,
    StepResult,
    StepStatus,
    TaskResult,
    TaskStatus,
)
from perceptai.events import EventBus, EventType
from perceptai.streaming import legacy_steps, to_legacy_sse


def _emit(type_, **payload):
    return EventBus().emit(type_, "sess", "task", **payload)


def test_task_started_maps_to_session_start():
    sse = to_legacy_sse(_emit(EventType.TASK_STARTED, instruction="go"))
    assert sse["type"] == "session_start"
    assert sse["instruction"] == "go"


def test_plan_created_maps_to_plan_with_pending_steps():
    sse = to_legacy_sse(
        _emit(EventType.PLAN_CREATED, steps=[{"description": "open", "action": "open_app"}])
    )
    assert sse["type"] == "plan"
    assert sse["steps"][0] == {
        "step_number": 1,
        "description": "open",
        "action": "open_app",
        "status": "pending",
    }


def test_step_completed_shape_and_healed_maps_to_completed():
    sse = to_legacy_sse(
        _emit(
            EventType.STEP_COMPLETED,
            step_number=3,
            description="click",
            action="click",
            status="healed",
            duration_s=1.2,
            error="",
            data={"extracted": "42"},
        )
    )
    assert sse["type"] == "step_complete"
    step = sse["step"]
    assert step["step_number"] == 3
    assert step["status"] == "completed"
    assert step["result"]["success"] is True
    assert step["result"]["extracted"] == "42"
    assert step["duration"] == 1.2


def test_failed_step_maps_to_failed():
    sse = to_legacy_sse(
        _emit(
            EventType.STEP_COMPLETED,
            step_number=1, description="x", action="click",
            status="failed", duration_s=0.5, error="not found", data={},
        )
    )
    assert sse["step"]["status"] == "failed"
    assert sse["step"]["result"]["success"] is False
    assert sse["step"]["result"]["error"] == "not found"


def test_task_completed_maps_to_complete():
    sse = to_legacy_sse(
        _emit(
            EventType.TASK_COMPLETED,
            status="completed", duration_s=9.5, total_steps=4,
            verification={"verified": True},
            summary="done well", report={"executive_summary": "done well"},
        )
    )
    assert sse == {
        "type": "complete",
        "status": "completed",
        "execution_time": 9.5,
        "total_steps": 4,
        "verification": {"verified": True},
        "summary": "done well",
        "report": {"executive_summary": "done well"},
    }


def test_every_event_type_has_a_mapping_or_none():
    for event_type in EventType:
        sse = to_legacy_sse(_emit(event_type))
        assert sse is None or "type" in sse


def test_legacy_steps_serialization():
    step = Step(action=ActionType.TYPE, description="type hi", params={"text": "hi"})
    result = TaskResult(
        task_id="t",
        instruction="i",
        status=TaskStatus.COMPLETED,
        steps=[
            StepResult(step=step, status=StepStatus.COMPLETED, index=1,
                       started_at="2026-01-01T00:00:00+00:00", duration_s=0.4,
                       data={"text": "hi"}),
        ],
    )
    legacy = legacy_steps(result)
    assert legacy == [
        {
            "step_number": 1,
            "description": "type hi",
            "action": "type",
            "status": "completed",
            "result": {"success": True, "text": "hi"},
            "timestamp": "2026-01-01T00:00:00+00:00",
            "duration": 0.4,
        }
    ]
