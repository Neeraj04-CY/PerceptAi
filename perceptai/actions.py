"""Physical input primitives. Dumb by design: no focus management, no
retries, no planning — the runtime owns those concerns. Every primitive
returns an ActionOutcome instead of raising.
"""
from __future__ import annotations

import time

from .config import EngineConfig
from .contracts import ActionOutcome


class ActionExecutor:
    def __init__(self, config: EngineConfig):
        self._config = config
        self._gui = None

    def _pyautogui(self):
        if self._gui is None:
            import pyautogui  # lazy: unavailable on headless hosts
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.3
            self._gui = pyautogui
        return self._gui

    def click(self, x: int, y: int, double: bool = False) -> ActionOutcome:
        try:
            gui = self._pyautogui()
            gui.moveTo(x, y, duration=0.2)
            if double:
                gui.doubleClick(x, y)
            else:
                gui.click(x, y)
            time.sleep(0.3)
            return ActionOutcome(ok=True, data={"x": x, "y": y})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def type_text(self, text: str) -> ActionOutcome:
        """Clipboard paste — reliable for all characters and layouts."""
        try:
            import pyperclip  # lazy
            gui = self._pyautogui()
            pyperclip.copy(text)
            time.sleep(0.15)
            gui.hotkey("ctrl", "v")
            time.sleep(0.3)
            return ActionOutcome(ok=True, data={"text": text, "method": "clipboard"})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def clear_and_type(self, text: str) -> ActionOutcome:
        try:
            self._pyautogui().hotkey("ctrl", "a")
            time.sleep(0.2)
            return self.type_text(text)
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def press(self, key: str) -> ActionOutcome:
        try:
            gui = self._pyautogui()
            if "+" in key:
                gui.hotkey(*key.split("+"))
            else:
                gui.press(key)
            return ActionOutcome(ok=True, data={"key": key})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def scroll(self, x: int, y: int, direction: str = "down", amount: int = 3) -> ActionOutcome:
        try:
            gui = self._pyautogui()
            gui.moveTo(x, y, duration=0.1)
            gui.scroll(-amount if direction == "down" else amount)
            return ActionOutcome(ok=True, data={"direction": direction})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def screen_size(self) -> tuple[int, int]:
        size = self._pyautogui().size()
        return size.width, size.height
