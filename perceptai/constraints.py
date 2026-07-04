"""Constraint management: policy-aware execution.

Constraints are predicates evaluated before a step runs. A denial is a
first-class outcome (the step fails with the constraint's reason and the
decision engine plans around it) — never a silent skip. Built-ins cover
the universal safety envelope; `register()` is the extension point for
organization policies (an Enterprise capability that needs no new
architecture: a policy is just another constraint).

Deterministic, observe-only, no LLM calls.
"""
from __future__ import annotations

from typing import Callable, Optional

from .config import EngineConfig
from .contracts import ActionType, ConstraintVerdict, Step, WorldState
from .fusion import normalize_text

# A constraint inspects an imminent step against the last observed world.
Constraint = Callable[[Step, Optional[WorldState]], ConstraintVerdict]

_INPUT_ACTIONS = {ActionType.CLICK, ActionType.TYPE, ActionType.CLEAR_TYPE, ActionType.PRESS}


class ConstraintManager:
    def __init__(self, config: EngineConfig):
        self._config = config
        self._constraints: list[tuple[str, Constraint]] = []
        if config.blocked_window_titles:
            self.register("blocked_windows", self._blocked_windows)

    def register(self, name: str, constraint: Constraint) -> None:
        """Extension point: org policies plug in as plain predicates."""
        self._constraints.append((name, constraint))

    def check_step(self, step: Step, world: Optional[WorldState]) -> ConstraintVerdict:
        """First denial wins. No constraints registered = everything allowed
        (the safety envelope beyond policy lives in budgets and honesty rules)."""
        for name, constraint in self._constraints:
            try:
                verdict = constraint(step, world)
            except Exception as e:
                # A broken policy must fail closed for input actions and
                # open for passive ones: we never act under an unevaluable
                # policy, but we may still look.
                if step.action in _INPUT_ACTIONS:
                    return ConstraintVerdict(
                        allowed=False, constraint=name,
                        reason=f"constraint could not be evaluated: {e}",
                    )
                continue
            if not verdict.allowed:
                verdict.constraint = verdict.constraint or name
                return verdict
        return ConstraintVerdict(allowed=True)

    # ------------------------------------------------------------ builtins

    def _blocked_windows(self, step: Step,
                         world: Optional[WorldState]) -> ConstraintVerdict:
        """Policy example shipped as a config list: never send input into a
        blocked application ('never touch the trading app'). Both the
        step's declared target and the observed focused window are checked —
        degraded window providers may not report focus."""
        if step.action not in _INPUT_ACTIONS:
            return ConstraintVerdict(allowed=True)
        targets = [
            str(step.params.get("window", "")),
            str(step.params.get("app", "")),
            world.focused_window if world is not None else "",
        ]
        for blocked in self._config.blocked_window_titles:
            b = normalize_text(str(blocked))
            if not b:
                continue
            for target in targets:
                t = normalize_text(target)
                if t and (b in t or t in b):
                    return ConstraintVerdict(
                        allowed=False, constraint="blocked_windows",
                        reason=f"input into blocked window '{target}' is not allowed",
                    )
        return ConstraintVerdict(allowed=True)
