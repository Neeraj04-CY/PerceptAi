"""Session-scoped screen capture and OCR.

PerceptionService is the pixel substrate of the world model: it captures
screenshots into the session workspace and runs OCR over them. It is one
perception PRIMITIVE, not the perception system — providers in
providers.py turn its output (and other sources) into observations that
fuse into a WorldState.

The only process-level shared resource is the EasyOCR model: its weights
are immutable and expensive (~10s load), so they are cached once per
process behind a lock.
"""
from __future__ import annotations

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
class Perception:
    text_blocks: list[TextBlock] = field(default_factory=list)
    screenshot_path: str = ""
    screenshot_size: tuple[int, int] = (0, 0)  # pixel size of the captured image
    timestamp: float = 0.0
    mode: str = "fast"

    @property
    def screen_text(self) -> str:
        return "\n".join(b.text for b in self.text_blocks)


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

    def _ocr(self, image_path: Path) -> tuple[list[TextBlock], tuple[int, int]]:
        import numpy as np  # lazy
        from PIL import Image  # lazy

        image = Image.open(image_path)
        width, height = image.size
        scale = max(width, height) / float(self._config.ocr_max_side)
        if scale > 1:
            image = image.resize((int(width / scale), int(height / scale)), Image.BILINEAR)
        else:
            scale = 1.0
        # Acquire the reader BEFORE locking: _get_reader takes the same
        # non-reentrant lock internally. The lock here only serializes
        # inference — EasyOCR readers are not thread-safe.
        reader = _get_reader()
        with _reader_lock:
            results = reader.readtext(np.array(image))
        blocks = []
        for bbox, text, confidence in results:
            # OCR ran on a downscaled image; map every coordinate back to
            # the full screenshot pixel space so clicks land where text is.
            x = int((bbox[0][0] + bbox[2][0]) / 2 * scale)
            y = int((bbox[0][1] + bbox[2][1]) / 2 * scale)
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=round(float(confidence), 3),
                    x=x,
                    y=y,
                    top_left=(int(bbox[0][0] * scale), int(bbox[0][1] * scale)),
                    bottom_right=(int(bbox[2][0] * scale), int(bbox[2][1] * scale)),
                )
            )
        return blocks, (width, height)

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
        blocks, size = self._ocr(path)
        result = Perception(
            text_blocks=blocks,
            screenshot_path=str(path),
            screenshot_size=size,
            timestamp=now,
            mode="fast",
        )
        self._cache.update({"timestamp": now, "region": region, "result": result})
        return result
