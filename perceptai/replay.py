"""Execution reconstructability — the flywheel's irreversible guarantee.

Five years from now the canonical event stream is PerceptAI's most valuable
asset: millions of real failure->hypothesis->recovery->outcome traces on live
enterprise estates, labelled with verified outcomes and the system's own
calibrated confidence. That corpus only exists if we EMIT enough today — you
cannot retroactively log what you never captured.

This module is the audit, not a second log. It consumes the ONE canonical
stream and reconstructs the seven dimensions an execution must be recoverable
along. A permanent test drives a real run and asserts every dimension is
present; if the pipeline ever stops emitting one, the test fails at build time,
before the missing data becomes an unrecoverable gap in the corpus.

The seven dimensions (per the Chapter IX audit):
    world      — what the agent perceived (snapshots + confidence)
    action     — what it did (executed steps + outcomes)
    reasoning  — why (typed decisions, beliefs, strategy)
    recovery   — how it recovered from failure (hypotheses + measured outcome)
    verification — whether the goal's criteria were met
    confidence — calibrated confidence throughout
    outcome    — the final verdict + business report

Reconstruction is pure over the event dicts (their persisted form), so it runs
identically against a live capture and the events table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .events import EventType

# Which event types furnish each dimension. A dimension is RECONSTRUCTABLE when
# at least one of its events is present with the fields the corpus needs.
WORLD = "world"
ACTION = "action"
REASONING = "reasoning"
RECOVERY = "recovery"
VERIFICATION = "verification"
CONFIDENCE = "confidence"
OUTCOME = "outcome"

DIMENSIONS = (WORLD, ACTION, REASONING, RECOVERY, VERIFICATION, CONFIDENCE, OUTCOME)

# Dimensions that must be present in EVERY completed run. Recovery is
# conditional — a clean run never fails, so "no recovery events" is correct,
# not a gap; it is audited only when a failure occurred.
ALWAYS_REQUIRED = (WORLD, ACTION, REASONING, VERIFICATION, CONFIDENCE, OUTCOME)


def _etype(event: dict) -> str:
    t = event.get("type")
    return t.value if isinstance(t, EventType) else str(t)


def _payload(event: dict) -> dict:
    return event.get("payload") or {}


@dataclass
class Reconstruction:
    """What could be rebuilt from a run's canonical events, and what could not."""
    present: dict[str, int] = field(default_factory=dict)   # dimension -> event count
    fields_seen: dict[str, set] = field(default_factory=dict)
    had_failure: bool = False

    def has(self, dimension: str) -> bool:
        return self.present.get(dimension, 0) > 0

    @property
    def missing(self) -> list[str]:
        """Required dimensions with no supporting events. Recovery is required
        only when the run actually experienced a failure."""
        required = set(ALWAYS_REQUIRED)
        if self.had_failure:
            required.add(RECOVERY)
        return sorted(d for d in required if not self.has(d))

    @property
    def complete(self) -> bool:
        return not self.missing

    def to_dict(self) -> dict:
        return {"present": dict(self.present), "missing": self.missing,
                "complete": self.complete, "had_failure": self.had_failure}


def reconstruct(events: Iterable[dict]) -> Reconstruction:
    """Rebuild the seven dimensions from a run's canonical event stream."""
    r = Reconstruction()

    def note(dimension: str, keys: Iterable[str], payload: dict) -> None:
        r.present[dimension] = r.present.get(dimension, 0) + 1
        seen = r.fields_seen.setdefault(dimension, set())
        seen.update(k for k in keys if k in payload)

    for event in events:
        etype = _etype(event)
        p = _payload(event)

        if etype == EventType.WORLD_SNAPSHOT.value:
            note(WORLD, ("focused_window", "elements", "confidence", "providers"), p)
            if "confidence" in p:
                note(CONFIDENCE, ("confidence",), p)

        elif etype == EventType.STEP_COMPLETED.value:
            note(ACTION, ("step_number", "action", "status", "data"), p)

        elif etype in (EventType.DECISION_MADE.value, EventType.STRATEGY_SELECTED.value,
                       EventType.BELIEF_UPDATED.value, EventType.PROGRESS_UPDATED.value):
            note(REASONING, ("decision", "reason", "factors", "strategy"), p)
            if "factors" in p or "confidence" in p:
                note(CONFIDENCE, ("factors", "confidence"), p)

        elif etype in (EventType.STEP_STARTED.value,):
            note(ACTION, ("step_number", "action"), p)

        elif etype in (EventType.HEALING_STARTED.value, EventType.HEALING_RESULT.value,
                       EventType.RECOVERY_STARTED.value, EventType.RECOVERY_COMPLETED.value,
                       EventType.HYPOTHESIS_CREATED.value, EventType.HYPOTHESIS_RESOLVED.value):
            note(RECOVERY, ("recovered", "hypothesis", "detail"), p)

        elif etype == EventType.VERIFICATION.value:
            note(VERIFICATION, ("verified", "confidence", "reason"), p)
            note(CONFIDENCE, ("confidence",), p)

        elif etype == EventType.TASK_COMPLETED.value:
            note(OUTCOME, ("status", "verification", "report", "summary"), p)

        elif etype == EventType.ERROR.value:
            r.had_failure = True

        # A failed step means recovery SHOULD have been attempted — mark the run
        # as having failed so the audit requires the recovery dimension.
        if etype == EventType.STEP_COMPLETED.value and p.get("status") == "failed":
            r.had_failure = True

    return r
