from perceptai.contracts import ActionType, Step, StepResult, StepStatus, TaskContext
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
    ctx.add_extraction("price", "$5")
    result = verifier.verify(ctx, [_ok("read_screen", find="price")])
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
