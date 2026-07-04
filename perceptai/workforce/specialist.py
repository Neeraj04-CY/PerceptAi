"""Specialists: deterministic execution units behind one interface.

A specialist receives a WorkOrder and a MissionContext and returns a
WorkResult — it never talks to other specialists and never schedules
work. Runtime-backed specialists are capability profiles over the ONE
runtime (AgentSession.run through a runner lease); compute specialists
are pure functions over shared mission state. New specialists implement
the same interface and register — zero runtime changes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..contracts import Evidence, GoalSpec, Task, TaskStatus
from .contracts import Mission, SpecialistProfile, WorkOrder, WorkResult, WorkStatus
from .evidence_graph import EvidenceGraph
from .scheduler import RunnerPool


@dataclass
class MissionContext:
    """What a specialist may see: the mission, shared read-mostly state.
    Specialists read this context; only the Executive writes results
    back into it — coordination is data flow, not dialogue."""
    mission: Mission
    goal: Optional[GoalSpec] = None
    facts: dict[str, str] = field(default_factory=dict)
    evidence_graph: EvidenceGraph = field(default_factory=EvidenceGraph)
    memory: Any = None
    workspace: Any = None


class Specialist:
    """The one interface every execution unit implements."""

    profile: SpecialistProfile

    def execute(self, order: WorkOrder, ctx: MissionContext) -> WorkResult:
        raise NotImplementedError

    def healthy(self) -> bool:
        return True


# ---------------------------------------------------------------- runtime

class RuntimeSpecialist(Specialist):
    """A capability profile over the one runtime. Executes a work order
    by composing an instruction and running it through a leased
    AgentSession — same execution loop, world model, reasoning and
    verification as any single task. Variants are profile data
    (capabilities, cost, instruction shaping), never subclasses."""

    def __init__(self, profile: SpecialistProfile, runners: RunnerPool,
                 instruction_prefix: str = ""):
        self.profile = profile
        self._runners = runners
        self._prefix = instruction_prefix

    def execute(self, order: WorkOrder, ctx: MissionContext) -> WorkResult:
        t0 = time.time()
        instruction = self._compose(order)
        with self._runners.lease(self.profile.resources) as session:
            if session is None:
                return WorkResult(
                    order_id=order.id, specialist=self.profile.name,
                    status=WorkStatus.FAILED,
                    error=f"no runner provides resources {self.profile.resources}",
                    duration_s=round(time.time() - t0, 2),
                )
            task = Task(instruction=instruction,
                        metadata={"mission_id": ctx.mission.id, "order_id": order.id})
            result = session.run(task)

        completed = result.status in (TaskStatus.COMPLETED, TaskStatus.UNVERIFIED)
        return WorkResult(
            order_id=order.id,
            specialist=self.profile.name,
            status=WorkStatus.COMPLETED if completed else WorkStatus.FAILED,
            summary=result.summary,
            outputs=self._outputs(order, result.findings, result.summary),
            evidence=list(result.findings),
            artifacts=list(result.artifacts),
            confidence=result.confidence,
            duration_s=round(time.time() - t0, 2),
            cost=self.profile.cost,
            error="; ".join(result.errors),
            metadata={"task_status": result.status.value, "task_id": result.task_id},
        )

    def _compose(self, order: WorkOrder) -> str:
        """One plain-English instruction for the runtime. Known inputs and
        expected outputs travel as context, not as a scripted workflow —
        the runtime still plans from the live screen."""
        parts = [f"{self._prefix}{order.objective}".strip()]
        if order.inputs:
            known = "; ".join(f"{k}: {v}" for k, v in list(order.inputs.items())[:8])
            parts.append(f"Already known: {known}.")
        if order.produces:
            parts.append(
                "Information to capture: " + ", ".join(order.produces[:8]) + ".")
        return " ".join(parts)

    @staticmethod
    def _outputs(order: WorkOrder, findings: list[Evidence], summary: str) -> dict[str, str]:
        """Map collected evidence onto the order's promised output keys.
        Label match first; an unmatched promise degrades to the summary so
        downstream orders still receive something honest."""
        outputs: dict[str, str] = {}
        for key in order.produces:
            needle = key.strip().lower()
            matched = [f.value for f in findings
                       if needle in f.label.strip().lower()
                       or f.label.strip().lower() in needle]
            if matched:
                outputs[key] = "; ".join(matched[:3])
            elif findings:
                outputs[key] = findings[0].value
            elif summary:
                outputs[key] = summary
        return outputs


# ---------------------------------------------------------------- compute

class MemoryRecallSpecialist(Specialist):
    """Pure compute: recalls persisted knowledge relevant to the order.
    Deterministic, instant, and often makes screen work unnecessary."""

    def __init__(self, profile: Optional[SpecialistProfile] = None):
        self.profile = profile or SpecialistProfile(
            name="memory-recall", capabilities=["memory_recall"],
            description="Recall persisted organizational knowledge.",
            cost=0.1, latency_s=1.0, confidence=0.9, resources=[],
        )

    def execute(self, order: WorkOrder, ctx: MissionContext) -> WorkResult:
        t0 = time.time()
        terms = list(dict.fromkeys(order.entities + order.requires + order.produces))
        rows: list[dict] = []
        if ctx.memory is not None:
            try:
                rows = ctx.memory.recall_knowledge(terms)
            except Exception:
                rows = []
        evidence = [
            Evidence(kind=str(r.get("attribute", "text")) or "text",
                     label=str(r.get("entity", "")),
                     value=str(r.get("value", "")),
                     source="memory",
                     confidence=float(r.get("confidence", 0.5) or 0.5))
            for r in rows if str(r.get("value", "")).strip()
        ]
        outputs = {
            key: next((e.value for e in evidence
                       if key.strip().lower() in e.label.strip().lower()), "")
            for key in order.produces
        }
        return WorkResult(
            order_id=order.id, specialist=self.profile.name,
            status=WorkStatus.COMPLETED,
            summary=(f"recalled {len(evidence)} knowledge item(s)"
                     if evidence else "no relevant knowledge in memory"),
            outputs={k: v for k, v in outputs.items() if v},
            evidence=evidence,
            confidence=0.9 if evidence else 0.3,
            duration_s=round(time.time() - t0, 2),
            cost=self.profile.cost,
        )


class EvidenceReviewSpecialist(Specialist):
    """Pure compute: the mission's reviewer. Deterministically audits the
    shared evidence graph — coverage, confidence, open conflicts — and
    returns a typed review the report and verification can rely on."""

    def __init__(self, profile: Optional[SpecialistProfile] = None):
        self.profile = profile or SpecialistProfile(
            name="evidence-review", capabilities=["verification"],
            description="Audit the shared evidence graph for consistency.",
            cost=0.1, latency_s=1.0, confidence=0.95, resources=[],
        )

    def execute(self, order: WorkOrder, ctx: MissionContext) -> WorkResult:
        t0 = time.time()
        summary = ctx.evidence_graph.summary()
        conflicts = ctx.evidence_graph.conflicts()
        verdict = "consistent" if not conflicts else f"{len(conflicts)} open conflict(s)"
        detail = (
            f"{summary['claims']} claim(s) across {summary['entities']} entity(ies) "
            f"from {summary['sources']} source(s); avg confidence "
            f"{summary['avg_confidence']}; {verdict}"
        )
        evidence = [Evidence(kind="text", label="evidence_review", value=detail,
                             source="evidence-review",
                             confidence=summary["avg_confidence"] or 0.5)]
        for conflict in conflicts[:5]:
            values = " vs ".join(v["value"] for v in conflict["values"][:3])
            evidence.append(Evidence(
                kind="text", label=f"conflict:{conflict['entity']}.{conflict['attribute']}",
                value=values, source="evidence-review", confidence=0.9,
            ))
        return WorkResult(
            order_id=order.id, specialist=self.profile.name,
            status=WorkStatus.COMPLETED,
            summary=detail,
            outputs={"review_verdict": verdict},
            evidence=evidence,
            confidence=max(0.1, 1.0 - 0.2 * len(conflicts)),
            duration_s=round(time.time() - t0, 2),
            cost=self.profile.cost,
        )


# ---------------------------------------------------------------- builtins

def builtin_specialists(runners: RunnerPool) -> list[Specialist]:
    """The built-in workforce. These register through the same interface
    and registry as any third-party plugin — nothing downstream knows
    their names."""
    return [
        RuntimeSpecialist(
            SpecialistProfile(
                name="research", capabilities=["research"],
                description="Explore sources and collect evidence for a report.",
                cost=3.0, latency_s=180.0, confidence=0.7,
                permissions=["desktop_input", "network"], resources=["desktop"],
            ),
            runners, instruction_prefix="Research and collect evidence: ",
        ),
        RuntimeSpecialist(
            SpecialistProfile(
                name="browser", capabilities=["browser"],
                description="Web navigation and on-page work.",
                cost=2.0, latency_s=120.0, confidence=0.7,
                permissions=["desktop_input", "network"], resources=["desktop"],
            ),
            runners,
        ),
        RuntimeSpecialist(
            SpecialistProfile(
                name="desktop", capabilities=["desktop"],
                description="Native application automation.",
                cost=2.0, latency_s=120.0, confidence=0.7,
                permissions=["desktop_input"], resources=["desktop"],
            ),
            runners,
        ),
        RuntimeSpecialist(
            SpecialistProfile(
                name="extraction", capabilities=["extraction"],
                description="Locate and capture specific values precisely.",
                cost=2.0, latency_s=120.0, confidence=0.75,
                permissions=["desktop_input", "network"], resources=["desktop"],
            ),
            runners, instruction_prefix="Find and extract exactly: ",
        ),
        MemoryRecallSpecialist(),
        EvidenceReviewSpecialist(),
    ]
