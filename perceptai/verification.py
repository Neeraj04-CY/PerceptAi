"""Outcome verification.

Checks derive from what the task actually did — the apps it opened, the
windows it focused, the input it sent, the information it was asked to
extract. No per-application alias tables, no special cases, and no side
effects: verification observes OS state, it never changes focus.
"""
from __future__ import annotations

from .contracts import (
    ActionType,
    StepResult,
    TaskContext,
    VerificationCheck,
    VerificationResult,
)
from .oscontrol import WindowManager


class Verifier:
    def __init__(self, windows: WindowManager):
        self._windows = windows

    def verify(self, context: TaskContext, steps: list[StepResult]) -> VerificationResult:
        checks: list[VerificationCheck] = []

        opened_apps = {
            str(r.step.params.get("app", "")).strip()
            for r in steps
            if r.step.action == ActionType.OPEN_APP and r.ok and r.step.params.get("app")
        }
        focused_windows = {
            str(r.step.params.get("window", "")).strip()
            for r in steps
            if r.step.action == ActionType.FOCUS_WINDOW and r.ok and r.step.params.get("window")
        }
        navigated = any(r.step.action == ActionType.NAVIGATE_URL and r.ok for r in steps)
        typed = any(r.step.action in (ActionType.TYPE, ActionType.CLEAR_TYPE) and r.ok for r in steps)
        read_steps = [r for r in steps if r.step.action == ActionType.READ_SCREEN]

        for app in opened_apps:
            title = self._windows.exists(app)
            checks.append(
                VerificationCheck(
                    name=f"window_exists:{app}",
                    passed=title is not None,
                    detail=title or f"no window title contains '{app}'",
                )
            )

        for window in focused_windows - opened_apps:
            title = self._windows.exists(window)
            checks.append(
                VerificationCheck(
                    name=f"window_exists:{window}",
                    passed=title is not None,
                    critical=False,  # focused windows may legitimately close during a task
                    detail=title or f"no window title contains '{window}'",
                )
            )

        if navigated and not opened_apps:
            # Best effort: a browser window should exist, but we cannot know
            # its title generically. Non-critical observation.
            any_window = bool(self._windows.list_windows())
            checks.append(
                VerificationCheck(
                    name="browser_navigation",
                    passed=any_window,
                    critical=False,
                    detail="navigation performed; window title unknown for default browser",
                )
            )

        if typed:
            # The last input target should still exist. Existence only —
            # verification must not steal focus.
            targets = [
                str(r.step.params.get("app") or r.step.params.get("window") or "").strip()
                for r in steps
                if r.step.action in (ActionType.TYPE, ActionType.CLEAR_TYPE) and r.ok
            ]
            target = next((t for t in reversed(targets) if t), "")
            if target:
                title = self._windows.exists(target)
                checks.append(
                    VerificationCheck(
                        name=f"input_target_exists:{target}",
                        passed=title is not None,
                        detail=title or f"input target '{target}' not found after execution",
                    )
                )

        if read_steps:
            checks.append(
                VerificationCheck(
                    name="extraction_present",
                    passed=bool(context.extractions),
                    detail=f"{len(context.extractions)} extraction(s) captured",
                )
            )

        if not checks:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                reason="No verifiable claims could be derived from the executed steps",
                checks=[],
            )

        critical = [c for c in checks if c.critical]
        passed_critical = all(c.passed for c in critical) if critical else all(c.passed for c in checks)
        passed_count = sum(1 for c in checks if c.passed)
        confidence = round(passed_count / len(checks), 3)

        failed = [c for c in checks if not c.passed]
        reason = (
            "All verification checks passed"
            if not failed
            else "Failed checks: " + "; ".join(f"{c.name} ({c.detail})" for c in failed)
        )
        return VerificationResult(
            verified=passed_critical, confidence=confidence, reason=reason, checks=checks
        )
