"""Outcome verification.

Checks derive from what the task actually did — the apps it opened, the
windows it focused, the input it sent, the information it was asked to
extract, the elements it grounded through the fused world model the
instant before acting — and from how the WORLD CHANGED between the first
and the last observation. No per-application alias tables, no special
cases, and no side effects: verification observes OS state, it never
changes focus.

Confidence is calibrated, not counted. Every check carries a strength —
measured where possible (grounded actions carry their fusion confidence),
a fixed source-weight otherwise — and the final confidence is noisy-OR
support from passed checks, multiplicatively discounted by failures: the
same corroboration/contradiction shape as fusion and beliefs. Independent
confirmations compound; a failed critical check crushes certainty; a
failed advisory check dents it visibly without zeroing honest positive
evidence. The verdict stays conservative: critical checks gate it, and
support below the floor is never claimed as verified.
"""
from __future__ import annotations

from typing import Optional

from .config import EngineConfig
from .contracts import (
    ActionType,
    STATE_CHANGING_ACTIONS,
    StepResult,
    TaskContext,
    VerificationCheck,
    VerificationResult,
    WorldState,
)
from .oscontrol import WindowManager

# Confidence is never reported as absolute certainty (matches fusion).
_CONFIDENCE_CAP = 0.99
# Below this support, positive evidence is too weak to claim the outcome:
# the run stays honestly UNVERIFIED rather than completed-on-a-hunch.
_VERIFIED_SUPPORT_FLOOR = 0.5
# Advisory failures contradict at a fraction of their strength — they are
# observations ("no visible change"), not proofs of failure.
_ADVISORY_CONTRADICTION = 0.4

# Fixed source-weights for derived checks (grounded actions are measured).
_STRENGTH_WINDOW_EXISTS = 0.9
_STRENGTH_FOCUSED_WINDOW = 0.6
_STRENGTH_BROWSER_NAV = 0.5
_STRENGTH_INPUT_TARGET = 0.8
_STRENGTH_EXTRACTION = 0.8
_STRENGTH_WORLD_CHANGED = 0.6
_STRENGTH_CRITERION = 0.85
_STRENGTH_JUDGE_DEGRADED = 0.2
# Per-step effect attribution is asymmetric: a change observed right after
# an action is strong causal confirmation; absence of visible change is
# only a mild contradiction (many legitimate actions render nothing).
_STRENGTH_EFFECT_CONFIRMED = 0.75
_STRENGTH_EFFECT_ABSENT = 0.55


def _clamp(strength: float) -> float:
    return max(0.0, min(float(strength), _CONFIDENCE_CAP))


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

    def verify(
        self,
        context: TaskContext,
        steps: list[StepResult],
        world_before: Optional[WorldState] = None,
        world_after: Optional[WorldState] = None,
    ) -> VerificationResult:
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
                    strength=_STRENGTH_WINDOW_EXISTS,
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
                    strength=_STRENGTH_FOCUSED_WINDOW,
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
                    strength=_STRENGTH_BROWSER_NAV,
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
                        # Advisory: dialogs legitimately close on submit, and the
                        # planner's app alias ('erp') rarely equals the real
                        # window title ('SAP Invoice Entry'). Absence discounts
                        # confidence; it never vetoes an otherwise-confirmed run.
                        critical=False,
                        strength=_STRENGTH_INPUT_TARGET,
                        detail=title or f"input target '{target}' not found after execution",
                    )
                )

        if read_steps:
            checks.append(
                VerificationCheck(
                    name="extraction_present",
                    passed=bool(context.evidence),
                    # Advisory: for information goals the criteria judge holds
                    # the critical line on missing evidence; an action task
                    # that read nothing en route is discounted, not vetoed.
                    critical=False,
                    strength=_STRENGTH_EXTRACTION,
                    detail=f"{len(context.evidence)} evidence item(s) captured",
                )
            )

        checks.extend(self._grounded_action_checks(steps))
        effect_checks = self._action_effect_checks(steps)
        checks.extend(effect_checks)
        if not effect_checks:
            # The coarse first-vs-last comparison only when no per-step
            # attribution exists: causal evidence supersedes correlation
            # (the world changing over the whole run must not credit a
            # click for what an app did on its own).
            checks.extend(self._world_change_checks(steps, world_before, world_after))
        checks.extend(self._judge_completion_criteria(context, steps))

        if not checks:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                reason="No verifiable claims could be derived from the executed steps",
                checks=[],
            )

        critical = [c for c in checks if c.critical]
        critical_ok = all(c.passed for c in critical)
        confidence = self._confidence(checks)
        verified = critical_ok and confidence >= _VERIFIED_SUPPORT_FLOOR

        failed = [c for c in checks if not c.passed]
        reason = (
            "All verification checks passed"
            if not failed
            else "Failed checks: " + "; ".join(f"{c.name} ({c.detail})" for c in failed)
        )
        return VerificationResult(
            verified=verified, confidence=confidence, reason=reason, checks=checks
        )

    @staticmethod
    def _confidence(checks: list[VerificationCheck]) -> float:
        """Noisy-OR support from passed checks, multiplicatively discounted
        by failed ones. Positive measured evidence never scores 0.0; nothing
        ever scores 1.0; a failed critical check contradicts at full
        strength, a failed advisory check at a fraction of it."""
        support = 1.0
        for c in checks:
            if c.passed:
                support *= 1.0 - _clamp(c.strength)
        support = 1.0 - support
        for c in checks:
            if not c.passed:
                factor = _clamp(c.strength) * (1.0 if c.critical else _ADVISORY_CONTRADICTION)
                support *= 1.0 - factor
        return round(min(support, _CONFIDENCE_CAP), 3)

    @staticmethod
    def _grounded_action_checks(steps: list[StepResult]) -> list[VerificationCheck]:
        """Execution evidence: a successful element-targeted action whose
        target the fused world model resolved the instant before acting is
        positive, measured evidence of the outcome — the same epistemic
        position a human is in right after clicking a button. Strength is
        the recorded grounding confidence, so weak perception never
        inflates certainty. Advisory: grounding corroborates the outcome,
        it never overrides a failed critical check."""
        checks: list[VerificationCheck] = []
        for r in steps:
            if not r.ok:
                continue
            element = str(r.data.get("element") or "").strip()
            try:
                grounding = float(r.data.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                grounding = 0.0
            if not element or grounding <= 0.0:
                continue
            sources = [str(s) for s in (r.data.get("sources") or [])]
            checks.append(
                VerificationCheck(
                    name=f"action_grounded:{element[:60]}",
                    passed=True,
                    critical=False,
                    strength=grounding,
                    detail=(
                        f"'{element}' resolved at {grounding:.2f} confidence"
                        + (f" by {', '.join(sources)}" if sources else "")
                    ),
                )
            )
        return checks

    @staticmethod
    def _action_effect_checks(steps: list[StepResult]) -> list[VerificationCheck]:
        """Causal evidence: the runtime attributes each post-action world
        diff to the step that caused it (StepResult.data['effect']). An
        observed change right after an action is the strongest verification
        signal available at zero perception cost — the difference between
        'we clicked Save' and 'we clicked Save and watched the world
        respond'. Advisory both ways, asymmetric strength."""
        checks: list[VerificationCheck] = []
        for r in steps:
            if not r.ok:
                continue
            effect = r.data.get("effect")
            if not isinstance(effect, dict):
                continue
            changed = bool(effect.get("changed"))
            summary = str(effect.get("summary") or "")
            checks.append(
                VerificationCheck(
                    name=f"action_effect:{r.step.description[:60]}",
                    passed=changed,
                    critical=False,
                    strength=_STRENGTH_EFFECT_CONFIRMED if changed else _STRENGTH_EFFECT_ABSENT,
                    detail=summary or (
                        "world responded to this action" if changed
                        else "no observable change after this action"
                    ),
                )
            )
        return checks

    @staticmethod
    def _world_change_checks(
        steps: list[StepResult],
        world_before: Optional[WorldState],
        world_after: Optional[WorldState],
    ) -> list[VerificationCheck]:
        """World-state comparison: successful state-changing actions must
        leave an observable trace. Advisory (non-critical) — perception
        gaps must not fail a task that other checks confirm."""
        if world_before is None or world_after is None:
            return []
        acted = any(r.step.action in STATE_CHANGING_ACTIONS and r.ok for r in steps)
        if not acted:
            return []
        from .world import WorldModel

        diff = WorldModel.diff(world_before, world_after)
        detail = diff.summary
        if diff.appeared_windows:
            detail += f" (appeared: {', '.join(diff.appeared_windows[:3])})"
        return [
            VerificationCheck(
                name="world_changed",
                passed=diff.changed,
                critical=False,
                strength=_STRENGTH_WORLD_CHANGED,
                detail=detail or "no observable change between first and last snapshot",
            )
        ]

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
            parsed, _raw = self._llm.complete_json(prompt, "verify", max_tokens=500)
        except Exception as e:
            return [VerificationCheck(name="criteria_judge", passed=False, critical=False,
                                      strength=_STRENGTH_JUDGE_DEGRADED,
                                      detail=f"judge unavailable: {e}")]
        if not isinstance(parsed, list):
            return [VerificationCheck(name="criteria_judge", passed=False, critical=False,
                                      strength=_STRENGTH_JUDGE_DEGRADED,
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
                    strength=_STRENGTH_CRITERION,
                    detail=str(verdict.get("reason", "")),
                )
            )
        return checks
