"""OS-level control: window management and application launching.

No hardcoded application paths and no per-app special cases. Apps are
resolved generically: PATH lookup, then the Windows App Paths registry,
then a Win+R fallback — the same mechanisms a user has for launching
arbitrary software.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .config import EngineConfig
from .contracts import ActionOutcome

# Chromium-family browsers the DOM provider can attach to over CDP.
_CHROMIUM_NAMES = ("chrome", "msedge", "edge", "chromium", "brave")

# OS shell windows that are always present and never task-relevant.
SHELL_WINDOW_TITLES = (
    "program manager",
    "windows input experience",
)


class WindowManager:
    def enumerate(self) -> list[dict]:
        """Rich window metadata: title, rect, z-order (front to back),
        focus, minimized state and owning process. Read-only."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        foreground = user32.GetForegroundWindow()
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        results: list[dict] = []
        process_names: dict[int, str] = {}

        def process_name(hwnd) -> str:
            try:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in process_names:
                    import psutil
                    process_names[pid.value] = psutil.Process(pid.value).name()
                return process_names[pid.value]
            except Exception:
                return ""

        def callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            lower = title.lower()
            if any(shell in lower for shell in SHELL_WINDOW_TITLES):
                return True
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            results.append(
                {
                    "title": title,
                    "rect": (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)),
                    "z_order": len(results),  # EnumWindows yields front-to-back
                    "focused": hwnd == foreground,
                    "minimized": bool(user32.IsIconic(hwnd)),
                    "process": process_name(hwnd),
                }
            )
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return results

    def list_windows(self) -> list[str]:
        import ctypes

        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
        )
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible

        windows: list[str] = []

        def callback(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    windows.append(buff.value)
            return True

        EnumWindows(EnumWindowsProc(callback), 0)
        return windows

    def exists(self, title_keyword: str) -> Optional[str]:
        """Return the first non-shell window title containing the keyword."""
        keyword = title_keyword.lower()
        for title in self.list_windows():
            lower = title.lower()
            if any(shell in lower for shell in SHELL_WINDOW_TITLES):
                continue
            if keyword in lower:
                return title
        return None

    def focus(self, title_keyword: str) -> ActionOutcome:
        import ctypes

        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
        )
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible

        found: list[int] = []
        keyword = title_keyword.lower()

        def callback(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                if keyword in buff.value.lower():
                    found.append(hwnd)
            return True

        EnumWindows(EnumWindowsProc(callback), 0)

        if not found:
            return ActionOutcome(ok=False, error=f"Window '{title_keyword}' not found")

        hwnd = found[0]
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        return ActionOutcome(ok=True, data={"window": title_keyword})


class AppLauncher:
    def __init__(self, config: EngineConfig, windows: WindowManager):
        self._config = config
        self._windows = windows

    def resolve(self, app_name: str) -> Optional[str]:
        """Resolve an app name to an executable path, generically."""
        name = app_name.strip().lower()
        exe = shutil.which(name) or shutil.which(f"{name}.exe")
        if exe:
            return exe
        try:
            import winreg
        except ImportError:
            return None
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe"
                with winreg.OpenKey(root, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    value = str(value).strip('"')
                    if value and os.path.exists(value):
                        return value
            except OSError:
                continue
        return None

    def open(self, app_name: str) -> ActionOutcome:
        try:
            exe = self.resolve(app_name)
            if exe:
                subprocess.Popen([exe])
                if self._wait_for_window(app_name):
                    return ActionOutcome(ok=True, data={"app": app_name, "method": "resolved"})
                return ActionOutcome(
                    ok=True, data={"app": app_name, "method": "resolved", "note": "window not confirmed"}
                )

            # Win+R fallback: works for anything the shell can launch.
            import pyautogui  # lazy
            pyautogui.hotkey("win", "r")
            time.sleep(0.8)
            pyautogui.typewrite(app_name.lower(), interval=0.05)
            pyautogui.press("enter")
            time.sleep(2)
            return ActionOutcome(ok=True, data={"app": app_name, "method": "win_r"})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def _wait_for_window(self, app_name: str) -> bool:
        deadline = time.time() + self._config.window_appear_timeout_s
        while time.time() < deadline:
            if self._windows.exists(app_name):
                time.sleep(0.5)  # settle
                return True
            time.sleep(0.5)
        return False

    def navigate(self, url: str) -> ActionOutcome:
        try:
            # Prefer a debuggable Chromium so the DOM provider can attach —
            # structural web perception "just works" without operator setup.
            if self._config.browser_debug_launch and self._config.dom_enabled:
                exe = self._resolve_chromium()
                if exe:
                    subprocess.Popen(self._chromium_debug_command(exe, url))
                    time.sleep(2)
                    return ActionOutcome(ok=True, data={
                        "url": url, "browser": exe, "debuggable": True})

            browser = self._config.preferred_browser
            if browser:
                exe = self.resolve(browser)
                if exe:
                    subprocess.Popen([exe, url])
                    time.sleep(2)
                    return ActionOutcome(ok=True, data={"url": url, "browser": browser})
            import webbrowser
            webbrowser.open(url)
            time.sleep(2)
            return ActionOutcome(ok=True, data={"url": url, "browser": "default"})
        except Exception as e:
            return ActionOutcome(ok=False, error=str(e))

    def _resolve_chromium(self) -> Optional[str]:
        """Find a Chromium-family browser, honoring preferred_browser first."""
        pref = (self._config.preferred_browser or "").strip().lower()
        candidates = ([pref] if pref else []) + list(_CHROMIUM_NAMES)
        for name in candidates:
            if name and any(c in name for c in _CHROMIUM_NAMES):
                exe = self.resolve(name)
                if exe:
                    return exe
        return None

    def _chromium_debug_command(self, exe: str, url: str) -> list[str]:
        """The launch command that opens the CDP port. A dedicated profile is
        required — without it a new launch just forwards the URL to an already
        running browser and the debug port never opens. Pure/testable."""
        profile = str(Path(tempfile.gettempdir()) / "perceptai-cdp-profile")
        return [
            exe,
            f"--remote-debugging-port={self._config.dom_debug_port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]
