"""Typed contracts for the workforce layer.

Every object that crosses a workforce boundary (planner -> executive,
executive -> specialist, specialist -> executive, executive -> consumers)
is defined here. Workers are deterministic execution units: they receive
a WorkOrder and return a WorkResult — coordination is data flow through
the Executive, never agent-to-agent dialogue.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..config import EngineConfig
from ..contracts import (  # noqa: F401  (re-exported workforce vocabulary)
    Artifact,
    Evidence,
    GoalSpec,
    TaskReport,
    _plain,
    utc_now_iso,
)


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


class MissionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"   # every effective objective completed
    PARTIAL = "partial"       # some objectives completed, some did not
    FAILED = "failed"         # no objective completed
    CANCELLED = "cancelled"


class WorkStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"   # policy denial or duplicate cancellation
    SKIPPED = "skipped"       # a dependency failed; this order never ran


class MissionDecisionType(str, Enum):
    DISPATCH = "dispatch"                  # assign ready orders to specialists
    WAIT = "wait"                          # work in flight; wait for a completion
    REASSIGN = "reassign"                  # retry a failed order elsewhere
    CANCEL_DUPLICATE = "cancel_duplicate"  # two orders produce the same thing
    FINISH = "finish"
    ABORT = "abort"


@dataclass
class SpecialistProfile:
    """What one execution unit is: capabilities, economics and needs.
    The Executive routes on this data — routing is never hardcoded."""
    name: str
    capabilities: list[str]
    description: str = ""
    cost: float = 1.0            # relative cost units per work order
    latency_s: float = 30.0      # expected seconds per work order
    confidence: float = 0.7      # baseline success expectation, 0..1
    permissions: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)  # exclusive leases, e.g. ["desktop"]
    max_concurrent: int = 1
    provider: str = "builtin"
    version: str = "1.0"

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class WorkOrder:
    """One schedulable unit of a mission. Dependencies are declared as
    data (requires/produces keys and explicit ids); the WorkGraph derives
    edges — the Executive schedules from the graph, never a static list."""
    objective: str
    capability: str
    id: str = field(default_factory=_short_id)
    entities: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)   # seeded values
    requires: list[str] = field(default_factory=list)      # data keys needed
    produces: list[str] = field(default_factory=list)      # data keys yielded
    depends_on: list[str] = field(default_factory=list)    # explicit order ids
    priority: int = 5                                      # 1 = highest
    expected_duration_s: float = 60.0
    confidence: float = 0.7
    max_attempts: int = 2
    # Mutable scheduling state, owned by the Executive.
    status: WorkStatus = WorkStatus.PENDING
    status_reason: str = ""
    assigned_to: str = ""
    attempts: int = 0

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class WorkResult:
    """What one specialist actually produced: artifacts and typed
    findings, never logs. The Executive folds outputs into the shared
    store and evidence into the mission evidence graph."""
    order_id: str
    specialist: str
    status: WorkStatus
    summary: str = ""
    outputs: dict[str, str] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    confidence: float = 0.0
    duration_s: float = 0.0
    cost: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == WorkStatus.COMPLETED

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class MissionDecision:
    """One scheduling-cycle verdict with the factors that produced it.
    Mirrors the runtime's Decision: data, not control flow — every one
    is emitted and replayable."""
    type: MissionDecisionType
    reason: str
    factors: dict[str, Any] = field(default_factory=dict)
    made_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class Mission:
    instruction: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceClaim:
    """One node of the evidence graph: entity -> attribute -> value with
    sources, honest confidence and versioning. Corroboration compounds
    confidence (noisy-OR); a credible different value opens a conflict
    instead of silently overwriting."""
    entity: str
    attribute: str
    value: str
    kind: str = "text"
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    first_seen: str = field(default_factory=utc_now_iso)
    last_seen: str = field(default_factory=utc_now_iso)
    version: int = 1
    supports: int = 1

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class EntityRelation:
    subject: str
    relation: str
    object: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class MissionMetrics:
    """Operational intelligence for one mission — outcomes and economics,
    not developer logs."""
    orders_total: int = 0
    orders_completed: int = 0
    orders_failed: int = 0
    orders_cancelled: int = 0
    orders_skipped: int = 0
    reassignments: int = 0
    duplicates_cancelled: int = 0
    peak_parallelism: int = 0
    cycles: int = 0
    cost_total: float = 0.0
    evidence_count: int = 0
    conflicts_open: int = 0
    specialist_utilization: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class MissionResult:
    """The mission deliverable: one grounded business report plus the
    complete, replayable record of how the workforce produced it."""
    mission_id: str
    instruction: str
    status: MissionStatus
    report: Optional[TaskReport] = None
    goal: Optional[GoalSpec] = None
    work: list[WorkResult] = field(default_factory=list)
    orders: list[WorkOrder] = field(default_factory=list)
    metrics: MissionMetrics = field(default_factory=MissionMetrics)
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class WorkforceConfig:
    """Every workforce tunable. Mission loops are budgeted exactly as
    runtime loops are: orders, cycles, wall clock and cost all bound."""
    engine: EngineConfig = field(default_factory=EngineConfig)
    max_parallel: int = 4
    max_work_orders: int = 16
    max_mission_cycles: int = 200
    max_mission_duration_s: float = 3600.0
    max_total_cost: float = 100.0
    wait_poll_s: float = 0.25
    decompose_model: str = ""  # empty = engine.planner_model

    @property
    def model(self) -> str:
        return self.decompose_model or self.engine.planner_model
