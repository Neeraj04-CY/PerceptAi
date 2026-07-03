from perceptai.config import EngineConfig
from perceptai.contracts import (
    ActionType,
    Evidence,
    GoalSpec,
    Step,
    StepResult,
    StepStatus,
    TaskContext,
)
from perceptai.verification import Verifier
from tests.conftest import FakeWindows


def _ok(action, **params):
    return StepResult(
        step=Step(action=ActionType(action), params=params),
        status=StepStatus.COMPLETED,
    )


def test_opened_app_window_must_exist():
    verifier = Verifier(FakeWindows(["Untitled - notepad"]))
    result = verifier.verify(TaskContext("open notepad"), [_ok("open_app", app="notepad")])
    assert result.verified
    assert result.confidence == 1.0


def test_missing_window_fails_verification():
    verifier = Verifier(FakeWindows([]))
    result = verifier.verify(TaskContext("open notepad"), [_ok("open_app", app="notepad")])
    assert not result.verified
    assert "notepad" in result.reason


def test_no_derivable_claims_is_unverified():
    verifier = Verifier(FakeWindows([]))
    result = verifier.verify(TaskContext("wait"), [_ok("wait", wait=1.0)])
    assert not result.verified
    assert result.checks == []


def test_extraction_check():
    verifier = Verifier(FakeWindows([]))
    ctx = TaskContext("read the price")
    ctx.add_evidence([Evidence(kind="price", label="price", value="$5")])
    result = verifier.verify(ctx, [_ok("read_screen", find="price")])
    assert result.verified


class _JudgeLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, prompt, model, max_tokens=500):
        from perceptai.llm import parse_json_reply
        return parse_json_reply(self.reply), self.reply


def _goal_ctx(output_format="report"):
    ctx = TaskContext("research prices")
    ctx.goal = GoalSpec(
        intent="research prices",
        output_format=output_format,
        completion_criteria=["price of product X is collected"],
    )
    ctx.add_evidence([Evidence(kind="price", label="product_x_price", value="$10", source="shop")])
    return ctx


def test_criteria_judge_pass_marks_verified():
    llm = _JudgeLLM('[{"criterion": 1, "met": true, "reason": "price present"}]')
    verifier = Verifier(FakeWindows([]), llm, EngineConfig(groq_api_key="x"))
    result = verifier.verify(_goal_ctx(), [_ok("read_screen", find="price")])
    assert result.verified
    assert any(c.name.startswith("criterion:") and c.passed for c in result.checks)


def test_criteria_judge_fail_blocks_information_goals():
    llm = _JudgeLLM('[{"criterion": 1, "met": false, "reason": "wrong product"}]')
    verifier = Verifier(FakeWindows([]), llm, EngineConfig(groq_api_key="x"))
    result = verifier.verify(_goal_ctx("report"), [_ok("read_screen", find="price")])
    assert not result.verified  # critical for report goals


def test_criteria_judge_advisory_for_action_goals():
    llm = _JudgeLLM('[{"criterion": 1, "met": false, "reason": "cannot confirm"}]')
    verifier = Verifier(FakeWindows(["notepad - x"]), llm, EngineConfig(groq_api_key="x"))
    ctx = _goal_ctx("action_confirmation")
    steps = [_ok("open_app", app="notepad")]
    result = verifier.verify(ctx, steps)
    assert result.verified  # window check passes; criterion is non-critical


def test_judge_garbage_degrades_without_blocking():
    llm = _JudgeLLM("not json at all")
    verifier = Verifier(FakeWindows(["notepad - x"]), llm, EngineConfig(groq_api_key="x"))
    ctx = _goal_ctx("report")
    ctx.goal.completion_criteria = ["x"]
    result = verifier.verify(ctx, [_ok("open_app", app="notepad")])
    # judge failure adds a non-critical failed check, window check still governs
    assert result.verified


def test_typing_checks_input_target():
    verifier = Verifier(FakeWindows(["myapp - editor"]))
    steps = [_ok("open_app", app="myapp"), _ok("type", text="hi", app="myapp")]
    result = verifier.verify(TaskContext("type into myapp"), steps)
    assert result.verified
    names = [c.name for c in result.checks]
    assert "input_target_exists:myapp" in names


def test_verification_never_calls_focus():
    windows = FakeWindows(["myapp - editor"])
    verifier = Verifier(windows)
    steps = [_ok("open_app", app="myapp"), _ok("type", text="hi", app="myapp")]
    verifier.verify(TaskContext("type"), steps)
    assert windows.focus_calls == []  # observation only, no side effects
