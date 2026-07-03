"""Session-scoped screen perception.

PerceptionService owns its screenshot workspace and cache — two sessions
never share mutable state. The only process-level shared resource is the
EasyOCR model: its weights are immutable and expensive (~10s load), so
they are cached once per process behind a lock.
"""
from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import EngineConfig
from .llm import LLMClient

_reader_lock = threading.Lock()
_shared_reader = None  # immutable model weights, process-level by design


def _get_reader():
    global _shared_reader
    with _reader_lock:
        if _shared_reader is None:
            import easyocr  # lazy: heavy import
            _shared_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _shared_reader


@dataclass
class TextBlock:
    text: str
    confidence: float
    x: int
    y: int
    top_left: tuple[int, int] = (0, 0)
    bottom_right: tuple[int, int] = (0, 0)


@dataclass
class ElementMatch:
    text: str
    x: int
    y: int
    confidence: float = 0.0
    kind: str = "text"

    @property
    def has_position(self) -> bool:
        return self.x > 0 and self.y > 0


@dataclass
class Perception:
    text_blocks: list[TextBlock] = field(default_factory=list)
    vision_elements: list[dict] = field(default_factory=list)
    page_context: str = "unknown"
    screenshot_path: str = ""
    timestamp: float = 0.0
    mode: str = "fast"

    @property
    def screen_text(self) -> str:
        return "\n".join(b.text for b in self.text_blocks)


def find_element(perception: Perception, query: str) -> Optional[ElementMatch]:
    """Locate an element by (sub)string match against vision elements,
    then OCR text blocks."""
    q = query.lower().strip()
    for el in perception.vision_elements:
        text = str(el.get("text", "")).lower()
        desc = str(el.get("description", "")).lower()
        pos = el.get("position") or {}
        if (q in text or q in desc) and pos:
            return ElementMatch(
                text=str(el.get("text", "")),
                x=int(pos.get("x", -1)),
                y=int(pos.get("y", -1)),
                confidence=float(el.get("confidence", 0.0)),
                kind=str(el.get("type", "element")),
            )
    for block in perception.text_blocks:
        if q in block.text.lower():
            return ElementMatch(text=block.text, x=block.x, y=block.y, confidence=block.confidence)
    return None


class PerceptionService:
    def __init__(self, config: EngineConfig, llm: LLMClient, workspace: Path):
        self._config = config
        self._llm = llm
        self._workspace = workspace
        self._shot_counter = 0
        self._cache: dict[str, Any] = {"timestamp": 0.0, "region": None, "result": None}

    @property
    def latest_screenshot(self) -> Optional[Path]:
        shots = sorted(self._workspace.glob("screen_*.png"))
        return shots[-1] if shots else None

    def capture(self, region=None) -> Path:
        from PIL import ImageGrab  # lazy: heavy import
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._shot_counter += 1
        path = self._workspace / f"screen_{self._shot_counter:05d}.png"
        ImageGrab.grab(bbox=region).save(path)
        self._prune_screenshots()
        return path

    def _prune_screenshots(self) -> None:
        shots = sorted(self._workspace.glob("screen_*.png"))
        for old in shots[: -self._config.screenshot_keep]:
            try:
                old.unlink()
            except OSError:
                pass

    def _ocr(self, image_path: Path) -> list[TextBlock]:
        import numpy as np  # lazy
        from PIL import Image  # lazy

        image = Image.open(image_path)
        width, height = image.size
        scale = max(width, height) / float(self._config.ocr_max_side)
        if scale > 1:
            image = image.resize((int(width / scale), int(height / scale)), Image.BILINEAR)
        with _reader_lock:
            results = _get_reader().readtext(np.array(image))
        blocks = []
        for bbox, text, confidence in results:
            x = int((bbox[0][0] + bbox[2][0]) / 2)
            y = int((bbox[0][1] + bbox[2][1]) / 2)
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=round(float(confidence), 3),
                    x=x,
                    y=y,
                    top_left=(int(bbox[0][0]), int(bbox[0][1])),
                    bottom_right=(int(bbox[2][0]), int(bbox[2][1])),
                )
            )
        return blocks

    def perceive_fast(self, region=None, force_refresh: bool = False) -> Perception:
        """OCR-only perception with a short per-session cache."""
        now = time.time()
        cached = self._cache["result"]
        if (
            not force_refresh
            and cached is not None
            and self._cache["region"] == region
            and (now - self._cache["timestamp"]) < self._config.fast_cache_ttl_s
        ):
            return cached

        path = self.capture(region)
        result = Perception(
            text_blocks=self._ocr(path),
            screenshot_path=str(path),
            timestamp=now,
            mode="fast",
        )
        self._cache.update({"timestamp": now, "region": region, "result": result})
        return result

    def perceive_full(self, region=None) -> Perception:
        """OCR + vision-LLM perception. Vision elements are enriched with
        OCR pixel coordinates by text match; unmatched elements get x=y=-1."""
        path = self.capture(region)
        blocks = self._ocr(path)
        ocr_map = {b.text.lower().strip(): b for b in blocks}

        image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        prompt = (
            'Analyze this screenshot. Return ONLY valid JSON:\n'
            '{"elements": [{"id": "el_001", "type": "button|input|dropdown|text|image|icon|table|link|menu",'
            ' "text": "exact visible text of this element", "clickable": true,'
            ' "description": "what this element does"}],'
            ' "page_context": "what app or page is this",'
            ' "primary_action": "main thing user can do here"}\n'
            "IMPORTANT: Use exact visible text. Return ONLY JSON."
        )
        parsed, _raw = self._llm.complete_vision_json(image_b64, prompt, self._config.vision_model)

        elements: list[dict] = []
        page_context = "unknown"
        if isinstance(parsed, dict):
            page_context = str(parsed.get("page_context", "unknown"))
            for el in parsed.get("elements", []) or []:
                text = str(el.get("text", "")).lower().strip()
                match = ocr_map.get(text)
                if match is None:
                    for ocr_text, block in ocr_map.items():
                        if text and (text in ocr_text or ocr_text in text):
                            match = block
                            break
                if match is not None:
                    el["position"] = {"x": match.x, "y": match.y}
                    el["confidence"] = match.confidence
                else:
                    el["position"] = {"x": -1, "y": -1}
                    el["confidence"] = 0.0
                elements.append(el)

        return Perception(
            text_blocks=blocks,
            vision_elements=elements,
            page_context=page_context,
            screenshot_path=str(path),
            timestamp=time.time(),
            mode="full",
        )
