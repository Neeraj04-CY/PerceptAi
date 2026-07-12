"""Adaptive perception (Phase 2): OCR runs only when it adds signal.

Autopsy of a real run: OCR cost ~7.1s/snapshot × 5 snapshots of a 39.9s
task, while UIA (169ms) grounded the same click at 0.99. These tests pin
the tiering: rich structured sources skip OCR; sparse ones fall back to
it; text-critical snapshots and full mode always include it; the DOM
provider backs off after finding no browser instead of paying the
connect timeout every frame.
"""
from __future__ import annotations

from perceptai.config import EngineConfig
from perceptai.contracts import BoundingBox, Observation, SourceType
from perceptai.providers import DomProvider, FrameContext, PerceptionProvider
from perceptai.world import WorldModel


class _Fake(PerceptionProvider):
    def __init__(self, name, source, elements=0):
        self.name = name
        self.source = source
        self.elements = elements
        self.calls = 0

    def observe(self, frame):
        self.calls += 1
        return [
            Observation(source=self.source, role="button", text=f"{self.name} {i}",
                        bbox=BoundingBox.around(100 + 15 * i, 200, 10), confidence=0.9)
            for i in range(self.elements)
        ]


def _cfg(**kw):
    return EngineConfig(groq_api_key="x", fast_cache_ttl_s=0.0, **kw)


def test_rich_structured_sources_skip_ocr():
    uia = _Fake("uia", SourceType.UIA, elements=20)
    ocr = _Fake("ocr", SourceType.OCR, elements=5)
    world = WorldModel(_cfg(), [uia, ocr])
    state = world.snapshot(force_refresh=True)
    assert uia.calls == 1
    assert ocr.calls == 0                       # skipped: 20 >= 12
    assert len(state.elements) == 20


def test_sparse_structured_sources_fall_back_to_ocr():
    uia = _Fake("uia", SourceType.UIA, elements=3)
    ocr = _Fake("ocr", SourceType.OCR, elements=8)
    world = WorldModel(_cfg(), [uia, ocr])
    world.snapshot(force_refresh=True)
    assert ocr.calls == 1                        # 3 < 12: pixels are the floor


def test_text_critical_always_includes_ocr():
    uia = _Fake("uia", SourceType.UIA, elements=30)
    ocr = _Fake("ocr", SourceType.OCR, elements=8)
    world = WorldModel(_cfg(), [uia, ocr])
    world.snapshot(force_refresh=True, text_critical=True)
    assert ocr.calls == 1


def test_adaptive_perception_can_be_disabled():
    uia = _Fake("uia", SourceType.UIA, elements=30)
    ocr = _Fake("ocr", SourceType.OCR, elements=8)
    world = WorldModel(_cfg(adaptive_perception=False), [uia, ocr])
    world.snapshot(force_refresh=True)
    assert ocr.calls == 1


# ------------------------------------------------------------ dom backoff

class _DeadReader:
    def __init__(self):
        self.reads = 0

    def read(self, *a, **k):
        self.reads += 1
        return None  # no debuggable browser


def test_dom_provider_backs_off_after_empty_round():
    cfg = _cfg(dom_enabled=True)
    reader = _DeadReader()
    dom = DomProvider(cfg, windows=None, reader=reader)
    assert dom.available()
    assert dom.observe(FrameContext(timestamp=0.0)) == []
    # The next several snapshots skip the dead browser entirely.
    skipped = sum(0 if dom.available() else 1 for _ in range(DomProvider._BACKOFF_SNAPSHOTS))
    assert skipped == DomProvider._BACKOFF_SNAPSHOTS
    # ...then it honestly retries (the browser may have appeared mid-run).
    assert dom.available()
