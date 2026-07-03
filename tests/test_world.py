"""WorldModel: provider orchestration, snapshot building, diffing,
element lookup and the planner-facing description."""
import pytest

from perceptai.contracts import BoundingBox, Observation, SourceType
from perceptai.providers import COST_CHEAP, COST_EXPENSIVE, FrameContext, PerceptionProvider
from perceptai.world import WorldModel
from tests.conftest import fast_config


class ScriptedProvider(PerceptionProvider):
    def __init__(self, name, source, observations, cost=COST_CHEAP,
                 is_available=True, error=None):
        self.name = name
        self.source = source
        self.cost = cost
        self._observations = observations
        self._available = is_available
        self._error = error
        self.calls = 0

    def available(self):
        return self._available

    def observe(self, frame: FrameContext):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._observations)


def _window(title, focused=False, z=0):
    return Observation(
        source=SourceType.OS_METADATA, role="window", text=title,
        attributes={"focused": focused, "z_order": z},
    )


def _button(name, box=(100, 100, 200, 130), focused=False):
    return Observation(
        source=SourceType.UIA, role="button", text=name,
        bbox=BoundingBox(*box), confidence=1.0,
        attributes={"focused": focused},
    )


def _world(*providers, **config_overrides):
    return WorldModel(fast_config(**config_overrides), list(providers))


def test_snapshot_builds_unified_state():
    world_model = _world(
        ScriptedProvider("meta", SourceType.OS_METADATA,
                         [_window("Notepad", focused=True), _window("Chrome", z=1)]),
        ScriptedProvider("uia", SourceType.UIA, [_button("Save", focused=True)]),
    )
    world = world_model.snapshot()
    assert [w.title for w in world.windows] == ["Notepad", "Chrome"]
    assert world.focused_window == "Notepad"
    assert len(world.elements) == 1
    assert world.focused_element_id == world.elements[0].id
    assert world.confidence > 0.9
    assert all(r.ok for r in world.providers)


def test_provider_failure_is_isolated_and_reported():
    world_model = _world(
        ScriptedProvider("broken", SourceType.UIA, [], error=RuntimeError("COM died")),
        ScriptedProvider("meta", SourceType.OS_METADATA, [_window("App")]),
    )
    world = world_model.snapshot()
    assert [w.title for w in world.windows] == ["App"]  # healthy source survived
    broken = next(r for r in world.providers if r.name == "broken")
    assert not broken.ok
    assert "COM died" in broken.error
    assert world_model.stats()["providers"]["broken"]["failures"] == 1


def test_expensive_providers_run_only_in_full_mode():
    vision = ScriptedProvider(
        "vision", SourceType.VISION,
        [Observation(source=SourceType.VISION, role="screen", text="a shop page")],
        cost=COST_EXPENSIVE,
    )
    world_model = _world(ScriptedProvider("meta", SourceType.OS_METADATA, []), vision)

    world_model.snapshot(mode="fast", force_refresh=True)
    assert vision.calls == 0

    full = world_model.snapshot(mode="full", force_refresh=True)
    assert vision.calls == 1
    assert full.page_context == "a shop page"


def test_unavailable_provider_is_skipped_silently():
    off = ScriptedProvider("uia", SourceType.UIA, [_button("X")], is_available=False)
    world = _world(off).snapshot()
    assert off.calls == 0
    assert world.elements == []


def test_diff_detects_window_appearance_and_focus_move():
    model = _world(ScriptedProvider("meta", SourceType.OS_METADATA, [_window("A", focused=True)]))
    before = model.snapshot(force_refresh=True)

    after_model = _world(
        ScriptedProvider("meta", SourceType.OS_METADATA,
                         [_window("A"), _window("B", focused=True, z=1)])
    )
    after = after_model.snapshot(force_refresh=True)

    diff = WorldModel.diff(before, after)
    assert diff.changed
    assert diff.appeared_windows == ["B"]
    assert diff.focus_changed
    assert diff.focus_after == "B"
    assert "B" in diff.summary


def test_diff_reports_no_change_for_identical_worlds():
    model = _world(ScriptedProvider("meta", SourceType.OS_METADATA,
                                    [_window("A", focused=True)]))
    before = model.snapshot(force_refresh=True)
    after = model.snapshot(force_refresh=True)
    diff = WorldModel.diff(before, after)
    assert not diff.changed


def test_find_prefers_interactive_over_plain_text():
    uia = ScriptedProvider("uia", SourceType.UIA, [_button("Submit", (300, 300, 380, 330))])
    ocr = ScriptedProvider(
        "ocr", SourceType.OCR,
        [Observation(source=SourceType.OCR, role="text", text="Press Submit to continue",
                     bbox=BoundingBox(10, 10, 300, 30), confidence=0.9)],
    )
    world = _world(uia, ocr).snapshot()
    found = WorldModel.find(world, "Submit")
    assert found is not None
    assert found.role == "button"
    assert found.center == (340, 315)


def test_find_returns_none_for_nonsense():
    world = _world(ScriptedProvider("uia", SourceType.UIA, [_button("Save")])).snapshot()
    assert WorldModel.find(world, "quantum flux capacitor") is None


def test_find_requires_position_by_default():
    vision_only = ScriptedProvider(
        "vision", SourceType.VISION,
        [Observation(source=SourceType.VISION, role="button", text="Ghost", bbox=None)],
    )
    world = _world(vision_only).snapshot()
    assert WorldModel.find(world, "Ghost") is None
    assert WorldModel.find(world, "Ghost", require_position=False) is not None


def test_describe_lists_interactive_elements_with_confidence():
    model = _world(
        ScriptedProvider("meta", SourceType.OS_METADATA, [_window("Editor", focused=True)]),
        ScriptedProvider("uia", SourceType.UIA, [_button("Save")]),
        ScriptedProvider(
            "ocr", SourceType.OCR,
            [Observation(source=SourceType.OCR, role="text", text="Document ready",
                         bbox=BoundingBox(10, 400, 200, 420), confidence=0.9)],
        ),
    )
    world = model.snapshot()
    view = model.describe(world)
    assert "Focused window: Editor" in view
    assert '"Save" [button]' in view
    assert "%" in view                       # confidence is visible
    assert "Document ready" in view


def test_snapshot_cache_respects_ttl_and_force():
    provider = ScriptedProvider("meta", SourceType.OS_METADATA, [_window("A")])
    model = WorldModel(fast_config(fast_cache_ttl_s=60.0), [provider])
    model.snapshot()
    model.snapshot()                          # served from cache
    assert provider.calls == 1
    model.snapshot(force_refresh=True)
    assert provider.calls == 2


def test_world_state_serializes_to_plain_json_types():
    import json
    model = _world(
        ScriptedProvider("meta", SourceType.OS_METADATA, [_window("A", focused=True)]),
        ScriptedProvider("uia", SourceType.UIA, [_button("Save")]),
    )
    world = model.snapshot()
    encoded = json.dumps(world.to_dict())     # must not raise
    assert "Save" in encoded
