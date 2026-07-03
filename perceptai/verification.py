"""Outcome verification.

Checks derive from what the task actually did — the apps it opened, the
windows it focused, the input it sent, the information it was asked to
extract. No per-application alias tables, no special cases, and no side
effects: verification observes OS state, it never changes focus.
"""
from __future__ import annotations

from typing import Optional

from .config import EngineConfig
from .contracts import (
    ActionType,
    StepResult,
    TaskContext,
    VerificationCheck,
    VerificationResult,
)
from .oscontrol import WindowManager


class Verifier:
    def __init__(
        self,
        windows: WindowManager,
        llm=None,
        config: Optional[EngineConfig] = None,
    ):
        self._windows = windows
        self._llm = llm
        self._config = config

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
                    passed=bool(context.evidence),
                    detail=f"{len(context.evidence)} evidence item(s) captured",
                )
            )

        checks.extend(self._judge_completion_criteria(context, steps))

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

    def _judge_completion_criteria(
        self, context: TaskContext, steps: list[StepResult]
    ) -> list[VerificationCheck]:
        """LLM-judge the goal's completion criteria against collected evidence.

        Critical only for information goals (report/data): unjudgeable action
        criteria must not regress action-task statuses. Judge failure degrades
        to a non-critical failed check — never raises."""
        goal = context.goal
        if goal is None or not goal.completion_criteria or self._llm is None or self._config is None:
            return []

        critical = goal.is_information_goal
        evidence_block = "\n".join(
            f"- [{e.kind}] {e.label}: {e.value} (source: {e.source or 'screen'})"
            for e in context.evidence[:30]
        ) or "No evidence collected."
        actions_block = "\n".join(
            f"- {r.step.description} [{r.step.action.value}]: {r.status.value}" for r in steps[-15:]
        ) or "No actions executed."
        criteria_block = "\n".join(f"{i+1}. {c}" for i, c in enumerate(goal.completion_criteria))

        prompt = f"""You are a strict task auditor. Judge whether each completion criterion is satisfied.

Goal: {goal.intent}

Completion criteria:
{criteria_block}

Evidence collected:
{evidence_block}

Actions executed:
{actions_block}

Return ONLY valid JSON:
[{{"criterion": 1, "met": true, "reason": "one sentence"}}]

Rules:
- Judge ONLY from the evidence and actions above. When in doubt, met=false.
Return ONLY the JSON array."""

        try:
            parsed, _raw = self._llm.complete_json(prompt, self._config.planner_model, max_tokens=500)
        except Exception as e:
            return [VerificationCheck(name="criteria_judge", passed=False, critical=False,
                                      detail=f"judge unavailable: {e}")]
        if not isinstance(parsed, list):
            return [VerificationCheck(name="criteria_judge", passed=False, critical=False,
                                      detail="judge returned no valid verdicts")]

        checks: list[VerificationCheck] = []
        for verdict in parsed:
            if not isinstance(verdict, dict):
                continue
            try:
                idx = int(verdict.get("criterion", 0)) - 1
                criterion = goal.completion_criteria[idx]
            except (TypeError, ValueError, IndexError):
                continue
            checks.append(
                VerificationCheck(
                    name=f"criterion:{criterion[:60]}",
                    passed=bool(verdict.get("met", False)),
                    critical=critical,
                    detail=str(verdict.get("reason", "")),
                )
            )
        return checks
