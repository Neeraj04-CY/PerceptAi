"""Execution budget accounting.

One ledger for every bounded resource: steps, replans, recoveries, LLM
calls, vision escalations and wall-clock time. The decision engine spends
against this view — nothing else re-derives budget state, and no loop
runs unbounded. Pure arithmetic over EngineConfig and per-run counters.
"""
from __future__ import annotations

import time

from .config import EngineConfig
from .contracts import BudgetSnapshot, ExecutionState


class ExecutionBudgetManager:
    def __init__(self, config: EngineConfig):
        self._config = config

    def snapshot(self, state: ExecutionState, started_at: float,
                 llm_calls: int, vision_calls: int) -> BudgetSnapshot:
        cfg = self._config
        elapsed = max(0.0, time.time() - started_at)
        snap = BudgetSnapshot(
            steps_used=state.steps_executed, steps_max=cfg.max_steps,
            replans_used=state.replans, replans_max=cfg.max_replans,
            recoveries_used=state.healings, recoveries_max=cfg.max_recovery_total,
            llm_calls_used=llm_calls, llm_calls_max=cfg.max_llm_calls,
            vision_calls_used=vision_calls, vision_calls_max=cfg.max_vision_escalations,
            elapsed_s=round(elapsed, 2), time_max_s=cfg.max_task_duration_s,
        )
        snap.pressure = self._pressure(snap)
        return snap

    @staticmethod
    def _pressure(snap: BudgetSnapshot) -> float:
        """The tightest budget defines pressure: one exhausted resource
        must stop the run even when every other budget is untouched."""
        ratios = [
            _ratio(snap.steps_used, snap.steps_max),
            _ratio(snap.replans_used, snap.replans_max),
            _ratio(snap.recoveries_used, snap.recoveries_max),
            _ratio(snap.llm_calls_used, snap.llm_calls_max),
            _ratio(snap.elapsed_s, snap.time_max_s),
        ]
        return round(min(1.0, max(ratios)), 3)

    # Affordability checks the decision engine consults before choosing
    # a spend. Vision has its own budget: escalation is the expensive path.

    @staticmethod
    def can_step(snap: BudgetSnapshot) -> bool:
        return snap.steps_used < snap.steps_max and snap.elapsed_s < snap.time_max_s

    @staticmethod
    def can_replan(snap: BudgetSnapshot) -> bool:
        return snap.replans_used < snap.replans_max and snap.elapsed_s < snap.time_max_s

    @staticmethod
    def can_recover(snap: BudgetSnapshot) -> bool:
        return snap.recoveries_used < snap.recoveries_max and snap.elapsed_s < snap.time_max_s

    @staticmethod
    def can_escalate_vision(snap: BudgetSnapshot) -> bool:
        return snap.vision_calls_used < snap.vision_calls_max

    @staticmethod
    def time_exceeded(snap: BudgetSnapshot) -> bool:
        return snap.elapsed_s >= snap.time_max_s


def _ratio(used: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return min(1.0, used / cap)
