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


# --------------------------------------------------------------- perception

class SourceType(str, Enum):
    """Where an observation came from. Providers contribute observations,
    never decisions — the fusion engine arbitrates between sources."""
    OS_METADATA = "os"
    UIA = "uia"
    OCR = "ocr"
    VISION = "vision"
    DOM = "dom"
    ACCESSIBILITY = "accessibility"
    CLIPBOARD = "clipboard"
    MEMORY = "memory"
    CUSTOM = "custom"


# Roles a user can act on. Fusion promotes elements to interactive when any
# source assigns one of these roles (or reports the element as clickable).
INTERACTIVE_ROLES = frozenset({
    "button", "link", "edit", "combo_box", "check_box", "radio_button",
    "menu_item", "menu", "tab", "list_item", "tree_item", "slider",
    "split_button", "spinner", "dropdown", "input", "icon",
})

# Roles that describe the environment rather than actionable elements.
# The world builder consumes these directly; they never become UIElements.
STRUCTURAL_ROLES = frozenset({"window", "cursor", "screen", "process"})


@dataclass(frozen=True)
class BoundingBox:
    """Pixel rectangle in the virtual-screen input coordinate space —
    the same space mouse actions use. Providers normalize into it."""
    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def around(cls, x: int, y: int, radius: int = 2) -> "BoundingBox":
        return cls(x - radius, y - radius, x + radius, y + radius)

    @property
    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def iou(self, other: "BoundingBox") -> float:
        ix = min(self.right, other.right) - max(self.left, other.left)
        iy = min(self.bottom, other.bottom) - max(self.top, other.top)
        if ix <= 0 or iy <= 0:
            return 0.0
        intersection = ix * iy
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0

    def scaled(self, fx: float, fy: float) -> "BoundingBox":
        return BoundingBox(
            int(self.left * fx), int(self.top * fy),
            int(self.right * fx), int(self.bottom * fy),
        )


@dataclass
class Observation:
    """One raw sighting from one perception provider. Observations are
    evidence about the world, not conclusions — fusion merges them."""
    source: SourceType
    role: str = "text"
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 1.0  # provider-native score, 0..1
    window: str = ""  # owning window title when known
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class WindowInfo:
    title: str
    focused: bool = False
    z_order: int = 0
    bbox: Optional[BoundingBox] = None
    process: str = ""
    minimized: bool = False


@dataclass
class UIElement:
    """A fused, deduplicated element of the world model. The best version
    of every observation — the planner never sees per-source duplicates."""
    id: str
    role: str
    name: str
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0  # fused confidence, 0..1
    sources: list[str] = field(default_factory=list)
    interactive: bool = False
    enabled: bool = True
    focused: bool = False
    value: str = ""
    window: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def has_position(self) -> bool:
        return self.bbox is not None

    @property
    def center(self) -> tuple[int, int]:
        return self.bbox.center if self.bbox is not None else (-1, -1)


@dataclass
class ProviderReport:
    """Health and cost record for one provider in one snapshot."""
    name: str
    source: str
    ok: bool = True
    observations: int = 0
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class WorldState:
    """The unified environment the planner reasons over. One world model,
    regardless of which providers contributed."""
    timestamp: float = 0.0
    mode: str = "fast"  # fast (cheap providers) | full (+ vision escalation)
    windows: list[WindowInfo] = field(default_factory=list)
    elements: list[UIElement] = field(default_factory=list)
    focused_window: str = ""
    focused_element_id: str = ""
    cursor: tuple[int, int] = (-1, -1)
    page_context: str = ""
    screenshot_path: str = ""
    providers: list[ProviderReport] = field(default_factory=list)
    confidence: float = 0.0  # overall perception confidence, 0..1

    @property
    def screen_text(self) -> str:
        """Flattened visible text, for LLM extraction and diffing."""
        seen: set[str] = set()
        lines: list[str] = []
        for el in self.elements:
            for chunk in (el.name, el.value):
                if chunk and chunk not in seen:
                    seen.add(chunk)
                    lines.append(chunk)
        return "\n".join(lines)

    @property
    def interactive_elements(self) -> list[UIElement]:
        return [el for el in self.elements if el.interactive]

    def to_dict(self) -> dict:
        return _plain(self)


@dataclass
class WorldDiff:
    """What changed between two world states. Verification asks 'did the
    world change?', not 'did we click?'."""
    changed: bool = False
    appeared_windows: list[str] = field(default_factory=list)
    disappeared_windows: list[str] = field(default_factory=list)
    focus_before: str = ""
    focus_after: str = ""
    focus_changed: bool = False
    elements_added: int = 0
    elements_removed: int = 0
    text_similarity: float = 1.0
    summary: str = ""

    def to_dict(self) -> dict:
        return _plain(self)


# ------------------------------------------------------------------- tasks

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
