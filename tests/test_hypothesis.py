"""HypothesisGenerator: multiple explanations, deterministic + LLM merge."""
from perceptai.contracts import (
    ActionType,
    BoundingBox,
    HealingPlan,
    Step,
    UIElement,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from perceptai.hypothesis import HypothesisGenerator

from tests.conftest import fast_config


def _click(find="Submit"):
    return Step(action=ActionType.CLICK, description=f"click {find}", params={"find": find})


def _world(elements=None, windows=None, focused=""):
    return WorldState(
        elements=elements or [],
        windows=[WindowInfo(title=w) for w in (windows or ["myapp"])],
        focused_window=focused,
    )


def test_dialog_appearance_suggests_modal():
    gen = HypothesisGenerator(fast_config())
    diff = WorldDiff(changed=True, appeared_windows=["Save Confirmation Dialog"])
    hypotheses = gen.generate(_click(), "Element 'Submit' not found on screen", _world(), diff)
    kinds = [h.kind for h in hypotheses]
    assert "modal_dialog" in kinds
    assert hypotheses[0].kind == "modal_dialog"  # ranked first


def test_focus_change_suggests_focus_lost_with_safe_recovery():
    gen = HypothesisGenerator(fast_config())
    diff = WorldDiff(changed=True, focus_changed=True,
                     focus_before="myapp", focus_after="Teams")
    hypotheses = gen.generate(_click(), "click failed", _world(), diff, expected_window="myapp")
    focus = next(h for h in hypotheses if h.kind == "focus_lost")
    assert focus.recovery_steps
    assert focus.recovery_steps[0].action == ActionType.FOCUS_WINDOW
    assert focus.recovery_steps[0].params["window"] == "myapp"


def test_sparse_screen_suggests_loading_with_wait():
    gen = HypothesisGenerator(fast_config())
    world = _world(elements=[], windows=["myapp"])
    hypotheses = gen.generate(_click(), "not found", world, WorldDiff(changed=False))
    loading = next(h for h in hypotheses if h.kind == "loading")
    assert loading.recovery_steps[0].action == ActionType.WAIT


def test_launcher_error_suggests_app_not_open():
    gen = HypothesisGenerator(fast_config())
    step = Step(action=ActionType.OPEN_APP, description="open x", params={"app": "x"})
    hypotheses = gen.generate(step, "cannot launch x", None, None)
    assert any(h.kind == "app_not_open" for h in hypotheses)


def test_similar_element_suggests_rename():
    gen = HypothesisGenerator(fast_config())
    el = UIElement(id="1", role="button", name="Submit Order",
                   bbox=BoundingBox(0, 0, 10, 10), confidence=0.9)
    # enough elements that the screen does not read as "loading"
    filler = [UIElement(id=str(i), role="text", name=f"filler {i}",
                        bbox=BoundingBox(0, 20 * i, 10, 20 * i + 10), confidence=0.9)
              for i in range(2, 6)]
    hypotheses = gen.generate(_click("Submit"), "Element 'Submit' not found on screen",
                              _world(elements=[el] + filler), WorldDiff(changed=False))
    renamed = next(h for h in hypotheses if h.kind == "element_renamed")
    assert "Submit Order" in renamed.explanation


def test_no_signals_yields_honest_unknown():
    gen = HypothesisGenerator(fast_config())
    world = _world(elements=[UIElement(id=str(i), role="text", name=f"t{i}", confidence=0.9)
                             for i in range(5)])
    hypotheses = gen.generate(
        Step(action=ActionType.PRESS, description="press enter", params={"key": "enter"}),
        "press failed", world, WorldDiff(changed=False),
    )
    assert [h.kind for h in hypotheses] == ["other"]
    assert not hypotheses[0].recovery_steps  # no blind recovery


def test_llm_agreement_compounds_probability():
    gen = HypothesisGenerator(fast_config())
    diff = WorldDiff(changed=True, focus_changed=True, focus_before="a", focus_after="b")
    candidates = gen.generate(_click(), "click failed", _world(), diff, expected_window="a")
    focus_before = next(h for h in candidates if h.kind == "focus_lost").probability

    llm = HealingPlan(diagnosis="focus moved to another window",
                      failure_type="focus_lost", confidence=0.8)
    merged = gen.merge_llm(candidates, llm, "click failed")
    focus_after = next(h for h in merged if h.kind == "focus_lost").probability
    assert focus_after > focus_before
    assert len(merged) == len(candidates)  # corroborated, not duplicated


def test_llm_alternatives_become_hypotheses():
    gen = HypothesisGenerator(fast_config())
    llm = HealingPlan(
        diagnosis="a modal is blocking", failure_type="modal_dialog", confidence=0.7,
        alternatives=[HealingPlan(diagnosis="app still loading",
                                  failure_type="loading", confidence=0.4)],
    )
    merged = gen.merge_llm([], llm, "click failed")
    assert {h.kind for h in merged} == {"modal_dialog", "loading"}
    assert all(h.source == "llm" for h in merged)


def test_resolution_records_evidence():
    gen = HypothesisGenerator(fast_config())
    hypotheses = gen.generate(_click(), "cannot launch x", None, None)
    h = hypotheses[0]
    gen.resolve(h, confirmed=False, reason="recovery failed")
    assert h.status == "rejected"
    assert h.resolution_reason == "recovery failed"
    assert h.evidence_against
