"""Phase 2 — causal verification: reactive simulation + per-step effect
attribution.

The simulated desktop responds to ACTIONS, not to the passage of
observations; the runtime attributes each post-action world diff to the
step that caused it; the verifier consumes that as measured causal
evidence. These tests pin all three layers.
"""
from __future__ import annotations

from perceptai.contracts import ActionType, Step, StepResult, StepStatus, TaskContext
from perceptai.simulation import SimulatedDesktop, build_simulated_session
from perceptai.verification import Verifier
from tests.conftest import FakeWindows


def _step(action, description, **params):
    return Step(action=ActionType(action), description=description, params=params)


# ------------------------------------------------------ simulated desktop

def test_legacy_screens_advance_per_snapshot():
    desk = SimulatedDesktop(screens=[["A"], ["B"], ["C"]])
    assert desk.screen_for_snapshot() == ["A"]
    assert desk.screen_for_snapshot() == ["B"]
    assert desk.screen_for_snapshot() == ["C"]
    assert desk.screen_for_snapshot() == ["C"]  # last screen repeats


def test_reactive_screen_persists_until_clicked():
    desk = SimulatedDesktop(screens=[["Alert", "OK"]],
                            reactions={"ok": ["Dashboard"]})
    assert desk.screen_for_snapshot() == ["Alert", "OK"]
    assert desk.screen_for_snapshot() == ["Alert", "OK"]  # persists, no auto-advance
    # Click at block 1's position ("OK"): layout is (100+10i, 200+10i).
    desk.click_at(110, 210)
    assert desk.screen_for_snapshot() == ["Dashboard"]
    assert desk.transitions == ["ok"]


def test_key_and_type_reactions():
    desk = SimulatedDesktop(screens=[["Modal"]],
                            reactions={"key:esc": ["Revealed"],
                                       "type:hello": ["hello"]})
    desk.key_pressed("esc")
    assert desk.screen_for_snapshot() == ["Revealed"]
    desk.text_typed("hello")
    assert desk.screen_for_snapshot() == ["hello"]


def test_unmatched_click_changes_nothing():
    desk = SimulatedDesktop(screens=[["Alert", "OK"]],
                            reactions={"ok": ["Dashboard"]})
    desk.screen_for_snapshot()
    desk.click_at(100, 200)  # block 0 = "Alert": no reaction declared
    assert desk.screen_for_snapshot() == ["Alert", "OK"]


# ------------------------------------------------- runtime attribution

def test_click_with_visible_effect_is_attributed_and_verified():
    """A click whose screen responds carries effect evidence, and the run
    verifies as COMPLETED on causal grounds."""
    session, fakes, events = build_simulated_session(
        plans=[[_step("click", "click save", find="Save", app="editor")]],
        screens=[["Save", "Cancel"]],
        windows=["editor - window"],
        reactions={"save": ["Saved", "Done"]},
    )
    result = session.run("save the document")
    click = next(r for r in result.steps if r.step.action == ActionType.CLICK)
    assert click.data.get("effect", {}).get("changed") is True
    assert result.status.value == "completed"
    effect_checks = [c for c in result.verification.checks
                     if c.name.startswith("action_effect:")]
    assert effect_checks and effect_checks[0].passed


def test_click_without_visible_effect_records_the_absence():
    session, fakes, events = build_simulated_session(
        plans=[[_step("click", "click save", find="Save", app="editor")]],
        screens=[["Save", "Cancel"]],
        windows=["editor - window"],
    )
    result = session.run("save the document")
    click = next(r for r in result.steps if r.step.action == ActionType.CLICK)
    effect = click.data.get("effect")
    assert effect is not None and effect["changed"] is False


# ------------------------------------------------- verifier consumption

def _ok_step(action, data=None, **params):
    return StepResult(step=Step(action=ActionType(action), params=params),
                      status=StepStatus.COMPLETED, data=data or {})


def test_effect_checks_supersede_coarse_world_change():
    """Per-step causal attribution replaces the first-vs-last comparison:
    the world changing over the whole run must not credit a click for
    what an app did on its own."""
    from perceptai.contracts import UIElement, WindowInfo, WorldState

    before = WorldState(windows=[WindowInfo(title="A")])
    after = WorldState(windows=[WindowInfo(title="A"), WindowInfo(title="B")],
                       elements=[UIElement(id="e1", role="text", name="New")])
    steps = [_ok_step("click", find="Save",
                      data={"element": "Save", "confidence": 0.9,
                            "effect": {"changed": False, "summary": ""}})]
    result = Verifier(FakeWindows([])).verify(
        TaskContext("save"), steps, world_before=before, world_after=after)
    names = [c.name for c in result.checks]
    assert any(n.startswith("action_effect:") for n in names)
    assert "world_changed" not in names


def test_confirmed_effect_outweighs_absent_effect():
    confirmed = Verifier(FakeWindows([])).verify(TaskContext("x"), [
        _ok_step("click", find="Save",
                 data={"element": "Save", "confidence": 0.8,
                       "effect": {"changed": True, "summary": "1 window appeared"}})])
    absent = Verifier(FakeWindows([])).verify(TaskContext("x"), [
        _ok_step("click", find="Save",
                 data={"element": "Save", "confidence": 0.8,
                       "effect": {"changed": False, "summary": ""}})])
    assert confirmed.confidence > absent.confidence
    assert confirmed.verified


def test_failed_step_contributes_no_effect_check():
    steps = [StepResult(step=Step(action=ActionType.CLICK, params={"find": "X"}),
                        status=StepStatus.FAILED,
                        data={"effect": {"changed": True, "summary": "spurious"}})]
    result = Verifier(FakeWindows([])).verify(TaskContext("x"), steps)
    assert all(not c.name.startswith("action_effect:") for c in result.checks)
