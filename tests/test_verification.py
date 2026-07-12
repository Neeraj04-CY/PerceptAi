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


def _ok(action, data=None, **params):
    return StepResult(
        step=Step(action=ActionType(action), params=params),
        status=StepStatus.COMPLETED,
        data=data or {},
    )


def test_opened_app_window_must_exist():
    verifier = Verifier(FakeWindows(["Untitled - notepad"]))
    result = verifier.verify(TaskContext("open notepad"), [_ok("open_app", app="notepad")])
    assert result.verified
    # Confidence is calibrated evidence, never absolute certainty.
    assert 0.85 <= result.confidence < 1.0


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


# ------------------------------------------------------- world-change checks

def _world_state(windows=(), focused="", elements=()):
    from perceptai.contracts import UIElement, WindowInfo, WorldState

    return WorldState(
        windows=[WindowInfo(title=t, focused=(t == focused)) for t in windows],
        elements=[
            UIElement(id=f"el_{i:03d}", role="text", name=name)
            for i, name in enumerate(elements, start=1)
        ],
        focused_window=focused,
    )


def test_world_change_confirms_state_changing_actions():
    verifier = Verifier(FakeWindows(["notepad"]))
    before = _world_state(windows=("Desktop",), focused="Desktop")
    after = _world_state(windows=("Desktop", "notepad"), focused="notepad",
                         elements=("File", "Edit"))
    result = verifier.verify(
        TaskContext("open notepad"), [_ok("open_app", app="notepad")],
        world_before=before, world_after=after,
    )
    world_check = next(c for c in result.checks if c.name == "world_changed")
    assert world_check.passed
    assert "notepad" in world_check.detail


def test_unchanged_world_after_actions_is_reported_not_fatal():
    verifier = Verifier(FakeWindows(["notepad"]))
    same = _world_state(windows=("notepad",), focused="notepad", elements=("File",))
    result = verifier.verify(
        TaskContext("open notepad"), [_ok("open_app", app="notepad")],
        world_before=same, world_after=same,
    )
    world_check = next(c for c in result.checks if c.name == "world_changed")
    assert not world_check.passed
    assert not world_check.critical      # advisory: never fails the task alone
    assert result.verified               # window_exists still confirms


def test_world_checks_skipped_without_snapshots_or_actions():
    verifier = Verifier(FakeWindows([]))
    result = verifier.verify(TaskContext("wait"), [_ok("wait", wait=1.0)],
                             world_before=_world_state(), world_after=_world_state())
    assert all(c.name != "world_changed" for c in result.checks)


# --------------------------------------------------- grounded-action evidence

def _grounded_click(element="Submit Order", confidence=0.9, sources=("ocr", "uia")):
    return _ok(
        "click",
        find=element,
        app="shop",
        data={"element": element, "role": "button",
              "confidence": confidence, "sources": list(sources)},
    )


def test_grounded_click_verifies_click_only_task():
    """A click grounded through the fused world model is positive evidence:
    a click-only task must not land UNVERIFIED at confidence 0.0."""
    verifier = Verifier(FakeWindows(["shop - window"]))
    result = verifier.verify(TaskContext("submit the order"), [_grounded_click()])
    grounded = [c for c in result.checks if c.name.startswith("action_grounded:")]
    assert grounded and grounded[0].passed and not grounded[0].critical
    assert result.verified
    assert 0.5 <= result.confidence < 1.0


def test_grounded_click_with_unchanged_world_discounts_but_verifies():
    """'No visible change' is a contradiction observation, not proof of
    failure: confidence is dented, the verdict holds."""
    verifier = Verifier(FakeWindows(["shop - window"]))
    same = _world_state(windows=("shop - window",), focused="shop - window",
                        elements=("Submit Order", "Cancel"))
    result = verifier.verify(TaskContext("submit the order"), [_grounded_click()],
                             world_before=same, world_after=same)
    world_check = next(c for c in result.checks if c.name == "world_changed")
    assert not world_check.passed
    assert result.verified
    grounded_only = verifier.verify(TaskContext("submit the order"), [_grounded_click()])
    assert result.confidence < grounded_only.confidence  # discount is visible


def test_weak_grounding_stays_unverified_but_not_zero():
    """Weak perception never inflates certainty — and honest positive
    evidence is never reported as zero confidence."""
    verifier = Verifier(FakeWindows(["shop - window"]))
    result = verifier.verify(
        TaskContext("submit"), [_grounded_click(confidence=0.3)])
    assert not result.verified
    assert 0.0 < result.confidence < 0.5


def test_failed_critical_check_crushes_grounded_confidence():
    """Grounding corroborates; it never overrides a failed critical check."""
    verifier = Verifier(FakeWindows([]))  # opened app has no window: critical fail
    steps = [_ok("open_app", app="phantom"), _grounded_click()]
    result = verifier.verify(TaskContext("open phantom and click"), steps)
    assert not result.verified
    assert result.confidence < 0.2


def test_confidence_is_never_certainty():
    """Many independent confirmations compound, but never reach 1.0."""
    verifier = Verifier(FakeWindows(["shop - window"]))
    steps = [_ok("open_app", app="shop")] + [
        _grounded_click(element=f"Button {i}", confidence=0.95) for i in range(5)
    ]
    result = verifier.verify(TaskContext("do many things"), steps)
    assert result.verified
    assert result.confidence <= 0.99


def test_ungrounded_click_contributes_no_grounded_check():
    verifier = Verifier(FakeWindows([]))
    result = verifier.verify(TaskContext("click"), [_ok("click", find="Submit")])
    assert all(not c.name.startswith("action_grounded:") for c in result.checks)


def test_failed_criterion_outweighs_grounding_alone():
    """The Spotify case, pinned: a click grounded at 0.99 whose stated
    completion criterion is judged unmet (and whose effect was absent)
    must NOT verify — 'clicked toward it' is not 'achieved it'."""
    llm = _JudgeLLM('[{"criterion": 1, "met": true, "reason": "app open"},'
                    ' {"criterion": 2, "met": false, "reason": "no evidence it is playing"}]')
    verifier = Verifier(FakeWindows(["Spotify Free"]), llm, EngineConfig(groq_api_key="x"))
    ctx = TaskContext("open spotify and play the playlist")
    ctx.goal = GoalSpec(
        intent="open spotify and play the playlist",
        output_format="action_confirmation",
        completion_criteria=["Spotify is open", "The playlist is playing"],
    )
    steps = [
        _ok("focus_window", window="Spotify Free"),
        _ok("click", find="playlist",
            data={"element": "Low Cortisol - playlist", "confidence": 0.99,
                  "sources": ["uia", "ocr"],
                  "effect": {"changed": False, "summary": "3 element(s) new, 4 gone"}}),
    ]
    result = verifier.verify(ctx, steps)
    assert not result.verified          # honest: Review, not Completed
    assert result.confidence < 0.5
