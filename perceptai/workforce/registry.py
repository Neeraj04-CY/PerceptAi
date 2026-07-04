"""The specialist registry: the workforce's plugin surface.

Specialists register (directly or via `perceptai.specialists` entry
points) and are discovered by capability. Each record tracks live
workload and measured performance so routing can prefer what actually
works. Nothing in the Executive or scheduler names a specialist —
adding one requires zero runtime changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .contracts import SpecialistProfile, WorkResult
from .specialist import Specialist


@dataclass
class SpecialistRecord:
    specialist: Specialist
    active: int = 0
    completed: int = 0
    failed: int = 0
    total_duration_s: float = 0.0
    last_error: str = ""
    profile: SpecialistProfile = field(init=False)

    def __post_init__(self) -> None:
        self.profile = self.specialist.profile

    @property
    def attempts(self) -> int:
        return self.completed + self.failed

    def measured_success_rate(self) -> Optional[float]:
        """Only meaningful with a few samples; otherwise routing falls
        back to the profile's baseline confidence."""
        if self.attempts < 3:
            return None
        return self.completed / self.attempts

    def workload_fraction(self) -> float:
        limit = max(1, self.profile.max_concurrent)
        return min(1.0, self.active / limit)

    def snapshot(self) -> dict:
        return {
            "name": self.profile.name,
            "capabilities": list(self.profile.capabilities),
            "active": self.active,
            "completed": self.completed,
            "failed": self.failed,
            "avg_duration_s": round(self.total_duration_s / self.attempts, 2)
            if self.attempts else 0.0,
            "healthy": self.healthy(),
        }

    def healthy(self) -> bool:
        try:
            return bool(self.specialist.healthy())
        except Exception:
            return False


class SpecialistRegistry:
    def __init__(self) -> None:
        self._records: dict[str, SpecialistRecord] = {}

    # ---------------------------------------------------------- populating

    def register(self, specialist: Specialist) -> SpecialistRecord:
        record = SpecialistRecord(specialist=specialist)
        self._records[record.profile.name] = record
        return record

    def discover(self, group: str = "perceptai.specialists") -> int:
        """Third-party plugin surface: every entry point in the group is a
        zero-argument factory returning a Specialist. A broken plugin is
        skipped, never fatal."""
        found = 0
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            selected = eps.select(group=group) if hasattr(eps, "select") \
                else eps.get(group, [])
        except Exception:
            return 0
        for ep in selected:
            try:
                specialist = ep.load()()
                if isinstance(getattr(specialist, "profile", None), SpecialistProfile):
                    self.register(specialist)
                    found += 1
            except Exception:
                continue
        return found

    # ------------------------------------------------------------- reading

    def get(self, name: str) -> Optional[SpecialistRecord]:
        return self._records.get(name)

    def records(self) -> list[SpecialistRecord]:
        return [self._records[name] for name in sorted(self._records)]

    def capabilities(self) -> list[str]:
        seen: list[str] = []
        for record in self.records():
            for capability in record.profile.capabilities:
                if capability not in seen:
                    seen.append(capability)
        return seen

    def candidates(self, capability: str) -> list[SpecialistRecord]:
        """Healthy records that cover the capability, with concurrency
        headroom. Deterministic order (name)."""
        return [
            r for r in self.records()
            if capability in r.profile.capabilities
            and r.healthy()
            and r.active < max(1, r.profile.max_concurrent)
        ]

    # ------------------------------------------------------------ tracking

    def acquire(self, name: str) -> None:
        record = self._records.get(name)
        if record is not None:
            record.active += 1

    def release(self, name: str, result: WorkResult) -> None:
        record = self._records.get(name)
        if record is None:
            return
        record.active = max(0, record.active - 1)
        record.total_duration_s += result.duration_s
        if result.ok:
            record.completed += 1
        else:
            record.failed += 1
            record.last_error = result.error

    def snapshot(self) -> list[dict]:
        return [record.snapshot() for record in self.records()]
