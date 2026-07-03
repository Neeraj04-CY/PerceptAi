"""Fusion engine: many observations in, one element out. Pure logic."""
from perceptai.contracts import BoundingBox, Observation, SourceType
from perceptai.fusion import FusionEngine, text_similarity
from tests.conftest import fast_config


def _engine(**overrides):
    return FusionEngine(fast_config(**overrides))


def _uia_button(name="Save", box=(100, 100, 180, 130), **attrs):
    return Observation(
        source=SourceType.UIA, role="button", text=name,
        bbox=BoundingBox(*box), confidence=1.0,
        window="App", attributes={"enabled": True, **attrs},
    )


def _ocr_text(text="Save", box=(110, 105, 170, 125), confidence=0.85):
    return Observation(
        source=SourceType.OCR, role="text", text=text,
        bbox=BoundingBox(*box), confidence=confidence,
    )


def test_same_element_from_two_sources_is_merged_not_duplicated():
    elements = _engine().fuse([_uia_button(), _ocr_text()])
    assert len(elements) == 1
    el = elements[0]
    assert el.role == "button"          # role from the trusted source
    assert el.name == "Save"
    assert set(el.sources) == {"uia", "ocr"}
    assert el.interactive


def test_corroboration_raises_confidence_but_never_certainty():
    engine = _engine()
    alone = engine.fuse([_ocr_text()])[0].confidence
    corroborated = engine.fuse([_uia_button(), _ocr_text()])[0].confidence
    assert corroborated > alone
    assert corroborated <= 0.99


def test_distinct_elements_stay_distinct():
    elements = _engine().fuse([
        _uia_button("Save", (100, 100, 180, 130)),
        _uia_button("Cancel", (200, 100, 280, 130)),
    ])
    assert len(elements) == 2
    assert {e.name for e in elements} == {"Save", "Cancel"}


def test_containment_without_text_agreement_does_not_swallow():
    # A text line inside a large pane is not the pane.
    pane = Observation(
        source=SourceType.UIA, role="document", text="Report body",
        bbox=BoundingBox(0, 0, 800, 600), confidence=1.0,
    )
    line = _ocr_text("Quarterly revenue: $1.2M", box=(50, 200, 400, 220))
    elements = _engine().fuse([pane, line])
    assert len(elements) == 2


def test_vision_observation_anchors_to_positioned_cluster_by_text():
    vision = Observation(
        source=SourceType.VISION, role="button", text="Save",
        bbox=None, confidence=1.0,
        attributes={"description": "saves the document", "clickable": True},
    )
    elements = _engine().fuse([_ocr_text("Save"), vision])
    assert len(elements) == 1
    el = elements[0]
    assert el.has_position                     # anchored to the OCR box
    assert "vision" in el.sources
    assert el.attributes.get("description") == "saves the document"
    assert el.interactive                      # clickable from vision


def test_unanchored_vision_observation_becomes_positionless_element():
    vision = Observation(
        source=SourceType.VISION, role="image", text="company logo",
        bbox=None, confidence=1.0,
    )
    elements = _engine().fuse([vision])
    assert len(elements) == 1
    assert not elements[0].has_position
    assert elements[0].center == (-1, -1)


def test_ids_are_assigned_in_reading_order():
    elements = _engine().fuse([
        _ocr_text("bottom", box=(10, 500, 100, 520)),
        _ocr_text("top", box=(10, 10, 100, 30)),
    ])
    assert [e.id for e in elements] == ["el_001", "el_002"]
    assert elements[0].name == "top"


def test_element_cap_keeps_interactive_and_confident():
    noise = [
        _ocr_text(f"line {i}", box=(0, i * 30, 200, i * 30 + 20), confidence=0.4)
        for i in range(30)
    ]
    button = _uia_button("Submit", (300, 300, 380, 330))
    elements = _engine(world_max_elements=10).fuse(noise + [button])
    assert len(elements) == 10
    assert any(e.name == "Submit" for e in elements)


def test_text_similarity_handles_ocr_noise():
    assert text_similarity("Submit", "Submlt") > 0.82   # 1-char OCR misread
    assert text_similarity("  SAVE ", "save") == 1.0    # case/whitespace noise
    # Containment scores high by design; spatial checks keep side-by-side
    # controls like "Save" / "Save As" from merging (see distinct test).
    assert text_similarity("Save", "Save As") >= 0.85
    assert text_similarity("OK", "Cancel") < 0.3
