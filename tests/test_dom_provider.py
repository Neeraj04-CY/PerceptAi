"""Sprint 6 — the DOM perception provider. Pure over an injected reader:
no browser, no CDP, no websocket. The reader's real-screen coordinate math is
validated by the perception bench; here we prove the provider builds correct
observations, filters noise, and fuses with OCR (DOM wins role/name)."""
from __future__ import annotations

from perceptai.cdp import DomNode, DomSnapshot
from perceptai.contracts import BoundingBox, Observation, SourceType
from perceptai.fusion import FusionEngine
from perceptai.oscontrol import AppLauncher
from perceptai.providers import DomProvider, FrameContext
from tests.conftest import fast_config


class FakeReader:
    def __init__(self, snapshot):
        self._snap = snapshot
        self.calls: list = []

    def read(self, host, port, foreground_title, *, max_nodes, timeout_s):
        self.calls.append((host, port, foreground_title, max_nodes))
        return self._snap


class FakeWindows:
    pass


def _provider(snapshot, **cfg):
    config = fast_config(dom_enabled=True, dom_host="h", dom_debug_port=9222, **cfg)
    return DomProvider(config, FakeWindows(), reader=FakeReader(snapshot))


def _frame():
    return FrameContext(timestamp=0.0)


def _snapshot(nodes, origin=(100, 200), title="Example"):
    return DomSnapshot(url="https://example.com", title=title, origin=origin, nodes=nodes)


# ---------------------------------------------------------- observation build

def test_translates_viewport_rect_to_screen_and_maps_role():
    snap = _snapshot([DomNode(role="button", name="Submit", x=10, y=20, w=50, h=15,
                              focusable=True)])
    obs = _provider(snap).observe(_frame())
    assert len(obs) == 1
    o = obs[0]
    assert o.source == SourceType.DOM and o.role == "button" and o.text == "Submit"
    # origin (100,200) + viewport rect (10,20,50,15) -> screen box
    assert (o.bbox.left, o.bbox.top, o.bbox.right, o.bbox.bottom) == (110, 220, 160, 235)
    assert o.attributes["interactive"] is True and o.window == "Example"


def test_ax_roles_map_to_world_roles():
    snap = _snapshot([
        DomNode(role="textbox", name="Email", x=0, y=0, w=100, h=20),
        DomNode(role="link", name="Home", x=0, y=30, w=40, h=15),
        DomNode(role="checkbox", name="Agree", x=0, y=60, w=20, h=20),
    ])
    roles = {o.text: o.role for o in _provider(snap).observe(_frame())}
    assert roles == {"Email": "edit", "Home": "link", "Agree": "check_box"}


def test_unnamed_noise_is_filtered_but_unnamed_interactive_kept():
    snap = _snapshot([
        DomNode(role="text", name="", x=0, y=0, w=10, h=10),        # noise -> dropped
        DomNode(role="button", name="", x=0, y=20, w=30, h=30),     # icon button -> kept
        DomNode(role="heading", name="Welcome", x=0, y=60, w=80, h=20),  # named -> kept
    ])
    obs = _provider(snap).observe(_frame())
    roles = sorted(o.role for o in obs)
    assert roles == ["button", "text"]  # heading maps to text; empty text dropped


def test_none_snapshot_yields_nothing():
    assert _provider(None).observe(_frame()) == []


def test_available_respects_config():
    assert DomProvider(fast_config(dom_enabled=True), FakeWindows()).available() is True
    assert DomProvider(fast_config(dom_enabled=False), FakeWindows()).available() is False


def test_budget_and_config_passed_to_reader():
    snap = _snapshot([DomNode(role="button", name="Go", x=0, y=0, w=10, h=10)])
    reader = FakeReader(snap)
    DomProvider(fast_config(dom_enabled=True, dom_host="h", dom_debug_port=1234,
                            dom_max_elements=42), FakeWindows(), reader=reader).observe(_frame())
    assert reader.calls[0][:2] == ("h", 1234)
    assert reader.calls[0][3] == 42  # max_nodes budget forwarded


# ------------------------------------------------------- fusion with OCR

def test_dom_wins_role_and_name_over_ocr_when_fused():
    dom = Observation(source=SourceType.DOM, role="button", text="Submit",
                      bbox=BoundingBox(110, 220, 160, 235), confidence=1.0,
                      window="Example", attributes={"interactive": True, "enabled": True})
    ocr = Observation(source=SourceType.OCR, role="text", text="Submit",
                      bbox=BoundingBox(112, 222, 158, 233), confidence=0.85)
    elements = FusionEngine(fast_config()).fuse([dom, ocr])
    assert len(elements) == 1
    el = elements[0]
    assert el.role == "button"                 # DOM (trust 0.98) beats OCR
    assert set(el.sources) == {"dom", "ocr"}
    assert el.interactive and el.confidence <= 0.99


# ------------------------------------------------------ debuggable launch

def test_chromium_debug_command_opens_the_port():
    launcher = AppLauncher(fast_config(dom_debug_port=9222), windows=None)
    cmd = launcher._chromium_debug_command(r"C:\\chrome.exe", "https://example.com")
    assert cmd[0].endswith("chrome.exe")
    assert "--remote-debugging-port=9222" in cmd
    assert any(a.startswith("--user-data-dir=") for a in cmd)  # dedicated profile
    assert cmd[-1] == "https://example.com"
