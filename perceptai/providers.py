"""Perception providers — the plugin surface of the Universal Perception Layer.

Every source of knowledge about the screen (Windows UI Automation, OCR,
vision LLM, window metadata, future DOM/mobile/remote providers) is a
PerceptionProvider. Providers contribute Observations, never decisions:
fusion (fusion.py) arbitrates between sources and the world model
(world.py) is the only thing the planner ever sees.

Provider rules:
- observe() never raises into the engine; the world builder isolates
  failures per provider and records them in ProviderReports.
- Heavy imports (uiautomation, PIL) are lazy; available() is cheap.
- All coordinates are normalized to the virtual-screen input space —
  the same space mouse actions use.
"""
from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import EngineConfig
from .contracts import INTERACTIVE_ROLES, BoundingBox, Observation, SourceType
from .llm import LLMClient

# Providers by cost tier. "free"/"cheap" run on every snapshot; "expensive"
# providers run only on full-mode escalation. Latency is a feature.
COST_FREE = "free"
COST_CHEAP = "cheap"
COST_EXPENSIVE = "expensive"


@dataclass
class FrameContext:
    """Shared context for one snapshot pass. Providers may enrich it for
    providers that run after them (e.g. OCR publishes the screenshot path
    that the vision provider analyzes)."""
    timestamp: float
    region: Optional[tuple] = None
    force_refresh: bool = False
    screenshot_path: str = ""
    screenshot_size: tuple[int, int] = (0, 0)
    screen_size: tuple[int, int] = (0, 0)
    attributes: dict[str, Any] = field(default_factory=dict)


class PerceptionProvider(ABC):
    """One source of observations about the digital environment."""

    name: str = "provider"
    source: SourceType = SourceType.CUSTOM
    cost: str = COST_FREE

    def available(self) -> bool:
        return True

    @abstractmethod
    def observe(self, frame: FrameContext) -> list[Observation]:
        """Return raw observations for this frame. May raise — the world
        builder catches per-provider failures and records them."""


# ------------------------------------------------------------ os metadata

class WindowMetadataProvider(PerceptionProvider):
    """Windows, z-order, focus, cursor and screen geometry via Win32.
    Free, instant, and authoritative for everything it reports."""

    name = "window_metadata"
    source = SourceType.OS_METADATA
    cost = COST_FREE

    def __init__(self, windows):
        self._windows = windows  # WindowManager (or a test fake)

    def observe(self, frame: FrameContext) -> list[Observation]:
        enumerate_fn = getattr(self._windows, "enumerate", None)
        if callable(enumerate_fn):
            observations = self._observe_rich(enumerate_fn, frame)
        else:
            observations = self._observe_titles()
        return observations

    def _observe_titles(self) -> list[Observation]:
        """Degraded path for window managers that only expose titles."""
        from .oscontrol import SHELL_WINDOW_TITLES
        observations = []
        for z, title in enumerate(self._windows.list_windows()):
            lower = title.lower()
            if any(shell in lower for shell in SHELL_WINDOW_TITLES):
                continue
            observations.append(
                Observation(
                    source=self.source, role="window", text=title,
                    confidence=1.0, attributes={"z_order": z},
                )
            )
        return observations

    def _observe_rich(self, enumerate_fn, frame: FrameContext) -> list[Observation]:
        observations = []
        for info in enumerate_fn():
            attributes = {
                "z_order": info.get("z_order", 0),
                "focused": bool(info.get("focused", False)),
                "minimized": bool(info.get("minimized", False)),
                "process": info.get("process", ""),
            }
            bbox = None
            rect = info.get("rect")
            if rect and len(rect) == 4 and rect[2] > rect[0] and rect[3] > rect[1]:
                bbox = BoundingBox(*rect)
            observations.append(
                Observation(
                    source=self.source, role="window", text=str(info.get("title", "")),
                    bbox=bbox, confidence=1.0, attributes=attributes,
                )
            )
        cursor = self._cursor_pos()
        if cursor is not None:
            observations.append(
                Observation(source=self.source, role="cursor", confidence=1.0,
                            attributes={"x": cursor[0], "y": cursor[1]})
            )
        screen = self._screen_size()
        if screen is not None:
            frame.screen_size = screen
            observations.append(
                Observation(source=self.source, role="screen", confidence=1.0,
                            attributes={"width": screen[0], "height": screen[1]})
            )
        return observations

    @staticmethod
    def _cursor_pos() -> Optional[tuple[int, int]]:
        try:
            import ctypes
            from ctypes import wintypes
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return int(point.x), int(point.y)
        except Exception:
            return None

    @staticmethod
    def _screen_size() -> Optional[tuple[int, int]]:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception:
            return None


# -------------------------------------------------------------------- ocr

class OcrProvider(PerceptionProvider):
    """Visible text via EasyOCR. Cheap, universal (works on pixels of any
    app), but sees only text — roles and interactivity come from richer
    sources when they are available."""

    name = "ocr"
    source = SourceType.OCR
    cost = COST_CHEAP

    def __init__(self, config: EngineConfig, perception):
        self._config = config
        self._perception = perception  # PerceptionService (or a test fake)

    def observe(self, frame: FrameContext) -> list[Observation]:
        result = self._perception.perceive_fast(
            region=frame.region, force_refresh=frame.force_refresh
        )
        # Publish the frame pixels for downstream providers (vision).
        frame.screenshot_path = getattr(result, "screenshot_path", "") or frame.screenshot_path
        shot_size = getattr(result, "screenshot_size", (0, 0))

        # Screenshot pixels and input coordinates can disagree under DPI
        # virtualization; normalize OCR boxes into the input space.
        fx = fy = 1.0
        if (
            shot_size and frame.screen_size
            and shot_size[0] > 0 and shot_size[1] > 0
            and frame.screen_size[0] > 0 and frame.screen_size[1] > 0
            and shot_size != frame.screen_size
            and frame.region is None
        ):
            fx = frame.screen_size[0] / shot_size[0]
            fy = frame.screen_size[1] / shot_size[1]

        observations = []
        for block in result.text_blocks:
            text = block.text.strip()
            if not text:
                continue
            tl, br = block.top_left, block.bottom_right
            if br[0] > tl[0] and br[1] > tl[1]:
                bbox = BoundingBox(tl[0], tl[1], br[0], br[1]).scaled(fx, fy)
            else:
                # Degenerate box (e.g. legacy data): keep the center point.
                bbox = BoundingBox.around(int(block.x * fx), int(block.y * fy))
            observations.append(
                Observation(
                    source=self.source, role="text", text=text,
                    bbox=bbox, confidence=float(block.confidence),
                )
            )
        return observations


# -------------------------------------------------------------------- uia

# UIA ControlTypeName -> world-model role.
_UIA_ROLE_MAP = {
    "ButtonControl": "button",
    "SplitButtonControl": "split_button",
    "HyperlinkControl": "link",
    "EditControl": "edit",
    "ComboBoxControl": "combo_box",
    "CheckBoxControl": "check_box",
    "RadioButtonControl": "radio_button",
    "MenuItemControl": "menu_item",
    "MenuControl": "menu",
    "MenuBarControl": "menu",
    "TabItemControl": "tab",
    "ListItemControl": "list_item",
    "TreeItemControl": "tree_item",
    "SliderControl": "slider",
    "SpinnerControl": "spinner",
    "TextControl": "text",
    "ImageControl": "image",
    "TableControl": "table",
    "DataGridControl": "table",
    "DataItemControl": "list_item",
    "DocumentControl": "document",
    "StatusBarControl": "status_bar",
    "ToolBarControl": "toolbar",
    "TitleBarControl": "title_bar",
    "HeaderItemControl": "header",
    "ProgressBarControl": "progress_bar",
}

# Container roles we traverse but do not emit as elements (pure structure).
_UIA_CONTAINER_TYPES = {
    "PaneControl", "GroupControl", "WindowControl", "CustomControl",
    "ListControl", "TreeControl", "TabControl", "HeaderControl",
    "ScrollBarControl", "SemanticZoomControl", "AppBarControl",
}


class UiaProvider(PerceptionProvider):
    """Interactive element tree of the foreground window via Windows UI
    Automation. The highest-fidelity desktop source: real roles, real
    rectangles, real enabled/focus state — no pixel guessing.

    Budgeted hard: max nodes, max depth and a wall-clock limit, because a
    UIA walk over a complex app (Excel, browsers) can explode."""

    name = "uia"
    source = SourceType.UIA
    cost = COST_CHEAP

    def __init__(self, config: EngineConfig):
        self._config = config
        self._import_ok: Optional[bool] = None

    def available(self) -> bool:
        if not self._config.uia_enabled or sys.platform != "win32":
            return False
        if self._import_ok is None:
            try:
                import uiautomation  # noqa: F401  lazy: heavy COM import
                self._import_ok = True
            except Exception:
                self._import_ok = False
        return self._import_ok

    def observe(self, frame: FrameContext) -> list[Observation]:
        import threading

        import uiautomation as auto

        if threading.current_thread() is threading.main_thread():
            return self._walk(auto)
        # COM must be initialized per thread; API/SSE runs execute off-main.
        with auto.UIAutomationInitializerInThread(debug=False):
            return self._walk(auto)

    def _walk(self, auto) -> list[Observation]:
        deadline = time.time() + self._config.uia_time_budget_s
        root = auto.GetForegroundControl()
        if root is None:
            return []
        try:
            window_title = str(root.Name or "")
        except Exception:
            window_title = ""

        observations: list[Observation] = []
        queue: list[tuple[Any, int]] = [(root, 0)]
        visited = 0
        while queue and len(observations) < self._config.uia_max_elements:
            if time.time() > deadline:
                break
            control, depth = queue.pop(0)
            visited += 1
            obs = self._to_observation(control, window_title)
            if obs is not None:
                observations.append(obs)
            if depth < self._config.uia_max_depth:
                try:
                    children = control.GetChildren()
                except Exception:
                    children = []
                queue.extend((child, depth + 1) for child in children)
        return observations

    def _to_observation(self, control, window_title: str) -> Optional[Observation]:
        try:
            control_type = str(control.ControlTypeName)
            name = str(control.Name or "").strip()
            if control_type in _UIA_CONTAINER_TYPES:
                return None
            role = _UIA_ROLE_MAP.get(
                control_type, control_type.replace("Control", "").lower() or "unknown"
            )
            if not name and role in ("text", "image", "unknown"):
                return None  # unnamed decoration — noise
            rect = control.BoundingRectangle
            bbox = None
            if rect is not None and rect.right > rect.left and rect.bottom > rect.top:
                bbox = BoundingBox(int(rect.left), int(rect.top),
                                   int(rect.right), int(rect.bottom))
            if getattr(control, "IsOffscreen", False):
                return None
            attributes: dict[str, Any] = {"control_type": control_type}
            try:
                attributes["enabled"] = bool(control.IsEnabled)
            except Exception:
                pass
            try:
                attributes["focused"] = bool(control.HasKeyboardFocus)
            except Exception:
                pass
            automation_id = str(getattr(control, "AutomationId", "") or "")
            if automation_id:
                attributes["automation_id"] = automation_id
            return Observation(
                source=self.source, role=role, text=name, bbox=bbox,
                confidence=1.0, window=window_title, attributes=attributes,
            )
        except Exception:
            return None  # one broken COM node never kills the walk


# ------------------------------------------------------------------ dom

# Accessibility (ARIA) role -> world-model role. The AX tree gives clean
# semantics; this normalizes them into the same vocabulary UIA/OCR use so
# fusion can merge across sources.
_AX_ROLE_MAP = {
    "button": "button", "link": "link", "textbox": "edit", "searchbox": "edit",
    "textfield": "edit", "combobox": "combo_box", "listbox": "combo_box",
    "checkbox": "check_box", "switch": "check_box", "radio": "radio_button",
    "menuitem": "menu_item", "menuitemcheckbox": "menu_item",
    "menuitemradio": "menu_item", "menu": "menu", "menubar": "menu",
    "tab": "tab", "option": "list_item", "listitem": "list_item",
    "treeitem": "tree_item", "slider": "slider", "spinbutton": "spinner",
    "heading": "text", "img": "image", "image": "image", "text": "text",
    "columnheader": "header", "rowheader": "header",
}
# Roles worth reporting even when they carry no accessible name (icon buttons).
_AX_KEEP_UNNAMED = frozenset({
    "button", "link", "edit", "combo_box", "check_box", "radio_button",
    "menu_item", "tab", "slider", "spinner",
})


class DomProvider(PerceptionProvider):
    """Structural perception of the foreground Chromium tab via the Chrome
    DevTools Protocol accessibility tree. The highest-fidelity source on the
    web — real roles, names and rectangles from the page itself.

    Pixels stay the floor: when no debuggable browser is reachable the reader
    returns None and this provider contributes nothing. The reader (cdp.py)
    owns the CDP wire and the screen-coordinate mapping; everything here is a
    pure role map and a translate, so it unit-tests against a fake reader."""

    name = "dom"
    source = SourceType.DOM
    cost = COST_CHEAP

    def __init__(self, config: EngineConfig, windows, reader=None):
        self._config = config
        self._windows = windows
        self._reader = reader  # injected DomReader; built lazily by default

    def available(self) -> bool:
        return bool(self._config.dom_enabled)

    def _get_reader(self):
        if self._reader is None:
            from .cdp import CDPAccessibilityReader
            self._reader = CDPAccessibilityReader()
        return self._reader

    def observe(self, frame: FrameContext) -> list[Observation]:
        snapshot = self._get_reader().read(
            self._config.dom_host, self._config.dom_debug_port,
            self._foreground_title(),
            max_nodes=self._config.dom_max_elements,
            timeout_s=self._config.dom_time_budget_s,
        )
        if snapshot is None:
            return []
        ox, oy = snapshot.origin
        window = snapshot.title
        observations: list[Observation] = []
        for node in snapshot.nodes:
            role = _AX_ROLE_MAP.get(node.role, node.role or "unknown")
            name = node.name or node.value
            interactive = role in INTERACTIVE_ROLES or node.focusable
            if not name and role not in _AX_KEEP_UNNAMED and not interactive:
                continue  # unnamed non-interactive node — noise
            left, top = int(ox + node.x), int(oy + node.y)
            bbox = BoundingBox(left, top, left + int(node.w), top + int(node.h))
            if not bbox.valid:
                continue
            observations.append(Observation(
                source=self.source, role=role, text=name, bbox=bbox,
                confidence=1.0, window=window,
                attributes={
                    "interactive": interactive,
                    "enabled": not node.disabled,
                    "ax_role": node.role,
                    "value": node.value,
                },
            ))
        return observations

    def _foreground_title(self) -> str:
        """Best-effort foreground window title, so the reader attaches to the
        right tab. Empty is fine — the reader then picks the first page."""
        getter = getattr(self._windows, "foreground_title", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                return ""
        return ""


# ------------------------------------------------------------------ vision

class VisionProvider(PerceptionProvider):
    """Vision-LLM screen understanding. The escalation path: semantic
    descriptions of elements OCR cannot classify and UIA cannot see
    (canvas-rendered UIs, images, custom controls). Expensive — runs only
    in full-mode snapshots. Its observations carry no positions; fusion
    anchors them to positioned observations by text."""

    name = "vision"
    source = SourceType.VISION
    cost = COST_EXPENSIVE

    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def available(self) -> bool:
        return self._llm is not None

    def observe(self, frame: FrameContext) -> list[Observation]:
        if not frame.screenshot_path:
            return []
        import base64
        from pathlib import Path

        image_b64 = base64.b64encode(Path(frame.screenshot_path).read_bytes()).decode("utf-8")
        prompt = (
            'Analyze this screenshot. Return ONLY valid JSON:\n'
            '{"elements": [{"type": "button|input|dropdown|text|image|icon|table|link|menu",'
            ' "text": "exact visible text of this element", "clickable": true,'
            ' "description": "what this element does"}],'
            ' "page_context": "what app or page is this",'
            ' "primary_action": "main thing user can do here"}\n'
            "IMPORTANT: Use exact visible text. Return ONLY JSON."
        )
        parsed, _raw = self._llm.complete_vision_json(
            image_b64, prompt, self._config.vision_model
        )
        if not isinstance(parsed, dict):
            return []

        observations: list[Observation] = []
        page_context = str(parsed.get("page_context", "")).strip()
        if page_context:
            observations.append(
                Observation(source=self.source, role="screen", text=page_context,
                            confidence=1.0, attributes={"kind": "page_context"})
            )
        for el in parsed.get("elements", []) or []:
            if not isinstance(el, dict):
                continue
            text = str(el.get("text", "")).strip()
            description = str(el.get("description", "")).strip()
            if not text and not description:
                continue
            role = str(el.get("type", "text")).strip().lower() or "text"
            observations.append(
                Observation(
                    source=self.source, role=role, text=text, bbox=None,
                    confidence=1.0,
                    attributes={
                        "description": description,
                        "clickable": bool(el.get("clickable", False)),
                    },
                )
            )
        return observations


# ---------------------------------------------------------------- registry

def default_providers(
    config: EngineConfig, *, perception, windows, llm: Optional[LLMClient]
) -> list[PerceptionProvider]:
    """The built-in provider set, ordered so early providers can enrich the
    frame for later ones (metadata publishes screen size, OCR publishes the
    screenshot, vision consumes it)."""
    providers: list[PerceptionProvider] = [
        WindowMetadataProvider(windows),
        UiaProvider(config),
        DomProvider(config, windows),
        OcrProvider(config, perception),
    ]
    if llm is not None:
        providers.append(VisionProvider(config, llm))
    return providers
