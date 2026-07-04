"""Workspace, plan limits, mission policy and audit.

The enterprise foundation as extension points, not features: plans are
data (WorkforceLimits presets), approvals are a callable hook, audit is
a subscriber on the canonical event stream. Order-level denials reuse
ConstraintVerdict — denied work is CANCELLED with the policy named,
never disguised as a failure. Step-level policy remains the runtime's
ConstraintManager; nothing here duplicates it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..contracts import ConstraintVerdict, _plain
from ..events import EventBus, TaskEvent
from .contracts import SpecialistProfile, WorkOrder


@dataclass
class WorkspaceContext:
    """Who this mission runs for. Scopes memory, events and audit; the
    control plane later maps organizations/projects onto it without
    engine changes."""
    organization: str = "personal"
    project: str = "default"
    user: str = ""
    roles: list[str] = field(default_factory=list)
    plan: str = "starter"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class WorkforceLimits:
    """Plan boundaries as data. Tiers differ in numbers and allowlists,
    never in engine branches."""
    max_parallel: int = 2
    max_work_orders: int = 6
    max_mission_duration_s: float = 1800.0
    max_total_cost: float = 25.0
    allowed_capabilities: Optional[list[str]] = None  # None = all
    approval_capabilities: list[str] = field(default_factory=list)

    _PLANS = {
        "starter": dict(max_parallel=2, max_work_orders=6,
                        max_mission_duration_s=1800.0, max_total_cost=25.0),
        "builder": dict(max_parallel=4, max_work_orders=12,
                        max_mission_duration_s=3600.0, max_total_cost=100.0),
        "scale": dict(max_parallel=8, max_work_orders=24,
                      max_mission_duration_s=7200.0, max_total_cost=500.0),
        "enterprise": dict(max_parallel=16, max_work_orders=64,
                           max_mission_duration_s=14400.0, max_total_cost=5000.0),
    }

    @classmethod
    def for_plan(cls, plan: str) -> "WorkforceLimits":
        return cls(**cls._PLANS.get(plan.strip().lower(), cls._PLANS["starter"]))

    def to_dict(self) -> dict:
        return _plain(self)


# An approver receives the order and returns True to allow it. The
# default approves everything; approval chains and human checkpoints
# plug in here without engine changes.
Approver = Callable[[WorkOrder], bool]


class MissionPolicy:
    """Order-level policy. check_order gates dispatch; needs_approval
    routes through the approver hook. Verdicts reuse the runtime's
    ConstraintVerdict contract."""

    def __init__(self, limits: Optional[WorkforceLimits] = None,
                 workspace: Optional[WorkspaceContext] = None,
                 approver: Optional[Approver] = None):
        self.workspace = workspace or WorkspaceContext()
        self.limits = limits or WorkforceLimits.for_plan(self.workspace.plan)
        self._approver = approver

    def check_order(self, order: WorkOrder,
                    profile: Optional[SpecialistProfile] = None) -> ConstraintVerdict:
        allowed = self.limits.allowed_capabilities
        if allowed is not None and order.capability not in allowed:
            return ConstraintVerdict(
                allowed=False, constraint="capability_allowlist",
                reason=f"capability '{order.capability}' is not enabled for "
                       f"plan '{self.workspace.plan}'",
            )
        if self.needs_approval(order):
            if self._approver is None or not self._safe_approve(order):
                return ConstraintVerdict(
                    allowed=False, constraint="approval_required",
                    reason=f"capability '{order.capability}' requires approval "
                           f"and none was granted",
                )
        return ConstraintVerdict(allowed=True)

    def needs_approval(self, order: WorkOrder) -> bool:
        return order.capability in self.limits.approval_capabilities

    def _safe_approve(self, order: WorkOrder) -> bool:
        try:
            return bool(self._approver(order))
        except Exception:
            return False  # a broken approver denies; it never crashes a mission


class AuditLog:
    """Audit is a consumer of the one event stream, not a new system.
    Every event is stamped with the workspace and kept in order."""

    def __init__(self, workspace: WorkspaceContext):
        self._workspace = workspace
        self.entries: list[dict] = []

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(self._record)

    def _record(self, event: TaskEvent) -> None:
        entry = event.to_dict()
        entry["workspace"] = {
            "organization": self._workspace.organization,
            "project": self._workspace.project,
            "user": self._workspace.user,
        }
        self.entries.append(entry)

    def export(self) -> list[dict]:
        return list(self.entries)
