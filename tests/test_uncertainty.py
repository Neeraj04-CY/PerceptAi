"""UncertaintyTracker: typed doubt signals from world state."""
from perceptai.contracts import (
    ActionType,
    BoundingBox,
    ProviderReport,
    Step,
    StepResult,
    StepStatus,
    UIElement,
    WindowInfo,
    WorldDiff,
    WorldState,
)
from perceptai.uncertainty import UncertaintyTracker

from tests.conftest import fast_config


def _element(name, confidence=0.9, interactive=True):
    return UIElement(
        id=name, role="button" if interactive else "text", name=name,
        bbox=BoundingBox(0, 0, 10, 10), confidence=confidence, interactive=interactive,
    )


def _world(**overrides):
    defaults = dict(
        windows=[WindowInfo(title="app")],
        elements=[_element("Save"), _element("Cancel")],
        confidence=0.9,
    )
    defaults.update(overrides)
    return WorldState(**defaults)


def test_confident_world_produces_no_uncertainty():
    tracker = UncertaintyTracker(fast_config())
    score, signals = tracker.assess(_world())
    assert score == 0.0
    assert signals == []


def test_no_world_is_maximum_uncertainty():
    tracker = UncertaintyTracker(fast_config())
    score, signals = tracker.assess(None)
    assert score == 1.0


def test_low_world_confidence_is_a_signal():
    tracker = UncertaintyTracker(fast_config())
    world = _world(elements=[_element("Save", confidence=0.3)], confidence=0.3)
    score, signals = tracker.assess(world)
    assert any(s.kind == "low_perception_confidence" for s in signals)
    assert score > 0.0


def test_similar_labels_are_ambiguous():
    tracker = UncertaintyTracker(fast_config())
    world = _world(elements=[_element("Submit Order"), _element("Submit Query")])
    _, signals = tracker.assess(world)
    assert any(s.kind == "ambiguous_elements" for s in signals)


def test_identical_labels_are_ambiguous():
    tracker = UncertaintyTracker(fast_config())
    world = _world(elements=[_element("OK"), _element("OK")])
    _, signals = tracker.assess(world)
    assert any(s.kind == "ambiguous_elements" for s in signals)


def test_distinct_labels_are_not_ambiguous():
    tracker = UncertaintyTracker(fast_config())
    world = _world(elements=[_element("File"), _element("Help")])
    _, signals = tracker.assess(world)
    assert not any(s.kind == "ambiguous_elements" for s in signals)


def test_failed_provider_is_a_signal():
    tracker = UncertaintyTracker(fast_config())
    world = _world(providers=[ProviderReport(name="uia", source="uia", ok=False, error="COM error")])
    _, signals = tracker.assess(world)
    assert any(s.kind == "provider_failed" for s in signals)


def test_slow_provider_suggests_loading():
    tracker = UncertaintyTracker(fast_config())
    world = _world(providers=[ProviderReport(name="ocr", source="ocr", ok=True, latency_ms=20000)])
    _, signals = tracker.assess(world)
    assert any(s.kind == "slow_provider" for s in signals)


def test_empty_screen_is_a_signal():
    tracker = UncertaintyTracker(fast_config())
    _, signals = tracker.assess(WorldState())
    assert any(s.kind == "missing_window" for s in signals)


def test_successful_action_without_world_change_is_suspicious():
    tracker = UncertaintyTracker(fast_config())
    step = Step(action=ActionType.CLICK, description="click save", params={"find": "Save"})
    result = StepResult(step=step, status=StepStatus.COMPLETED)
    _, signals = tracker.assess(_world(), WorldDiff(changed=False), result)
    assert any(s.kind == "no_change_after_action" for s in signals)


def test_signals_compound_noisy_or():
    tracker = UncertaintyTracker(fast_config())
    world = _world(
        elements=[_element("OK"), _element("OK")],
        providers=[ProviderReport(name="uia", source="uia", ok=False, error="x")],
    )
    score, signals = tracker.assess(world, contradicted_beliefs=2)
    assert len(signals) >= 3
    assert 0.0 < score <= 0.99
    # noisy-OR: total exceeds any single severity
    assert score > max(s.severity for s in signals)
