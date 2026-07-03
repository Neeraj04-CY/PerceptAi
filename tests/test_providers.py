"""Built-in perception providers, tested against fakes — no COM, no LLM,
no screen access."""
import time

from perceptai.contracts import SourceType
from perceptai.perception import Perception, TextBlock
from perceptai.providers import (
    FrameContext,
    OcrProvider,
    VisionProvider,
    WindowMetadataProvider,
    default_providers,
)
from tests.conftest import FakeWindows, fast_config


def _frame(**kwargs):
    return FrameContext(timestamp=time.time(), **kwargs)


# ------------------------------------------------------------------- ocr

class _ScriptedPerception:
    def __init__(self, blocks, size=(0, 0), path=""):
        self._result = Perception(
            text_blocks=blocks, screenshot_path=path, screenshot_size=size
        )

    def perceive_fast(self, region=None, force_refresh=False):
        return self._result


def test_ocr_provider_emits_positioned_text_observations():
    blocks = [TextBlock("Save", 0.9, 140, 115, top_left=(100, 100), bottom_right=(180, 130))]
    provider = OcrProvider(fast_config(), _ScriptedPerception(blocks, path="shot.png"))
    frame = _frame()
    observations = provider.observe(frame)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.source == SourceType.OCR
    assert obs.text == "Save"
    assert obs.bbox.center == (140, 115)
    assert frame.screenshot_path == "shot.png"    # published for vision


def test_ocr_provider_normalizes_screenshot_to_input_space():
    # Screenshot is 2x the input coordinate space (DPI mismatch).
    blocks = [TextBlock("Save", 0.9, 200, 200, top_left=(180, 180), bottom_right=(220, 220))]
    provider = OcrProvider(
        fast_config(), _ScriptedPerception(blocks, size=(3840, 2160))
    )
    frame = _frame(screen_size=(1920, 1080))
    obs = provider.observe(frame)[0]
    assert obs.bbox.center == (100, 100)


def test_ocr_provider_keeps_point_for_degenerate_boxes():
    blocks = [TextBlock("Save", 0.9, 140, 115)]  # legacy zero-area corners
    provider = OcrProvider(fast_config(), _ScriptedPerception(blocks))
    obs = provider.observe(_frame())[0]
    assert obs.bbox is not None
    assert obs.bbox.center == (140, 115)


# ----------------------------------------------------------- os metadata

def test_metadata_provider_degrades_to_titles_only():
    provider = WindowMetadataProvider(FakeWindows(["Notepad - note", "Program Manager"]))
    observations = provider.observe(_frame())
    titles = [o.text for o in observations if o.role == "window"]
    assert titles == ["Notepad - note"]           # shell windows filtered


def test_metadata_provider_rich_path_reports_focus_and_screen():
    class RichWindows:
        def enumerate(self):
            return [
                {"title": "App", "rect": (0, 0, 800, 600), "z_order": 0,
                 "focused": True, "minimized": False, "process": "app.exe"},
            ]

    provider = WindowMetadataProvider(RichWindows())
    frame = _frame()
    observations = provider.observe(frame)
    window = next(o for o in observations if o.role == "window")
    assert window.attributes["focused"] is True
    assert window.attributes["process"] == "app.exe"
    assert window.bbox.width == 800
    # Cursor/screen come from live Win32 calls — present on Windows hosts.
    roles = {o.role for o in observations}
    assert "window" in roles


# ------------------------------------------------------------------ vision

class _VisionLLM:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls = 0

    def complete_vision_json(self, image_b64, prompt, model, max_tokens=1500):
        self.calls += 1
        return self._parsed, "raw"


def test_vision_provider_needs_a_screenshot():
    provider = VisionProvider(fast_config(), _VisionLLM({}))
    assert provider.observe(_frame()) == []       # no screenshot published


def test_vision_provider_parses_elements_and_page_context(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    llm = _VisionLLM({
        "elements": [
            {"type": "button", "text": "Checkout", "clickable": True,
             "description": "starts checkout"},
            {"type": "text", "text": "", "description": ""},   # empty -> dropped
        ],
        "page_context": "an online store",
    })
    provider = VisionProvider(fast_config(), llm)
    observations = provider.observe(_frame(screenshot_path=str(shot)))

    screen = next(o for o in observations if o.role == "screen")
    assert screen.text == "an online store"
    button = next(o for o in observations if o.role == "button")
    assert button.text == "Checkout"
    assert button.bbox is None                    # fusion anchors it by text
    assert button.attributes["clickable"] is True


def test_vision_provider_degrades_on_malformed_reply(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    provider = VisionProvider(fast_config(), _VisionLLM(None))
    assert provider.observe(_frame(screenshot_path=str(shot))) == []


# ---------------------------------------------------------------- registry

def test_default_providers_order_enriches_frame_left_to_right():
    providers = default_providers(
        fast_config(), perception=_ScriptedPerception([]),
        windows=FakeWindows([]), llm=_VisionLLM({}),
    )
    names = [p.name for p in providers]
    # Metadata first (publishes screen size), OCR before vision
    # (publishes the screenshot vision consumes).
    assert names.index("window_metadata") < names.index("ocr") < names.index("vision")
    assert "uia" in names
