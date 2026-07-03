"""Typed contracts for the PerceptAI runtime.

Every object that crosses a subsystem boundary (planner -> runtime,
runtime -> consumers, runtime -> verification) is defined here.
Loose dictionaries are allowed only inside a single module.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain(value: Any) -> Any:
    """Recursively convert dataclasses/enums into JSON-safe primitives."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    UNVERIFIED = "unverified"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HEALED = "healed"
    SKIPPED = "skipped"


class ActionType(str, Enum):
    OPEN_APP = "open_app"
    NAVIGATE_URL = "navigate_url"
    FOCUS_WINDOW = "focus_window"
    CLICK = "click"
    TYPE = "type"
    CLEAR_TYPE = "clear_type"
    PRESS = "press"
    WAIT = "wait"
    SCROLL = "scroll"
    READ_SCREEN = "read_screen"


# Planner dict keys that carry step parameters.
_STEP_PARAM_KEYS = ("app", "url", "window", "find", "text", "key", "wait", "direction")


@dataclass
class Step:
    action: ActionType
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "planner"  # planner | replan | healer

    @classmethod
    def from_planner_dict(cls, raw: dict, source: str = "planner") -> Optional["Step"]:
        """Validate one raw planner step. Returns None when the action is unknown."""
        try:
            action = ActionType(str(raw.get("action", "")).strip().lower())
        except ValueError:
            return None
        params = {k: raw[k] for k in _STEP_PARAM_KEYS if raw.get(k) not in (None, "")}
        return cls(action=action, description=str(raw.get("description", "")), params=params, source=source)


@dataclass
class ActionOutcome:
    """Result of one physical action primitive."""
    ok: bool
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    step: Step
    status: StepStatus
    index: int = 0  # 1-based execution order, includes healing steps
    started_at: str = ""
    duration_s: float = 0.0
    attempts: int = 1
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (StepStatus.COMPLETED, StepStatus.HEALED)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class PlannerOutput:
    steps: list[Step] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    raw: str = ""
    model: str = ""
    dropped: int = 0  # raw steps rejected during validation


@dataclass
class HealingPlan:
    diagnosis: str = ""
    failure_type: str = "other"
    steps: list[Step] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class VerificationCheck:
    name: str
    passed: bool
    critical: bool = True
    detail: str = ""


@dataclass
class VerificationResult:
    verified: bool
    confidence: float = 0.0
    reason: str = ""
    checks: list[VerificationCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class Evidence:
    """One piece of collected, sourced information. Evidence is the atomic
    unit of business value — reports are assembled from it, knowledge is
    persisted from it, completion criteria are judged against it."""
    kind: str  # price | title | name | date | email | link | table | number | text | other
    label: str
    value: str
    source: str = ""  # app, url or screen where it was observed
    confidence: float = 0.0
    collected_at: str = field(default_factory=utc_now_iso)


@dataclass
class GoalSpec:
    """What the user is actually trying to achieve — drives planning,
    verification and reporting. Produced once, before any execution."""
    intent: str
    deliverable: str = ""
    output_format: str = "action_confirmation"  # report | data | action_confirmation
    entities: list[str] = field(default_factory=list)
    required_info: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    success_definition: str = ""

    @property
    def is_information_goal(self) -> bool:
        return self.output_format in ("report", "data")


@dataclass
class TaskReport:
    """The business deliverable. Narrative fields are LLM-composed from
    collected evidence only; everything else is assembled deterministically."""
    executive_summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    artifacts: list["Artifact"] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class Artifact:
    kind: str  # screenshot | file | text
    path: str = ""
    description: str = ""


@dataclass
class Task:
    instruction: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Working memory for a single task run. Accumulate-only: evidence,
    sources and notes grow during execution and are never overwritten."""
    instruction: str
    goal: Optional[GoalSpec] = None
    facts: dict[str, str] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_evidence(self, items: list[Evidence]) -> None:
        for item in items:
            self.evidence.append(item)
            if item.label:
                self.facts[item.label] = item.value

    def add_source(self, source: str) -> None:
        source = source.strip()
        if source and source not in self.sources:
            self.sources.append(source)

    def add_note(self, note: str) -> None:
        if note:
            self.notes.append(note)

    @property
    def latest_extraction(self) -> str:
        return self.evidence[-1].value if self.evidence else ""


@dataclass
class ExecutionState:
    """Mutable per-run execution state. Owned by the engine, never module-level."""
    current_app: str = ""
    current_window: str = ""
    browser_opened: bool = False
    steps_executed: int = 0
    replans: int = 0
    healings: int = 0
    llm_calls: int = 0


@dataclass
class TaskResult:
    task_id: str
    instruction: str
    status: TaskStatus
    summary: str = ""
    goal: Optional[GoalSpec] = None
    report: Optional[TaskReport] = None
    findings: list[Evidence] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(self)
