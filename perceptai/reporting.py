"""Business report generation.

Narrative fields (executive summary, key findings, next actions) are
LLM-composed FROM COLLECTED EVIDENCE ONLY — the prompt forbids invention.
Evidence, sources, confidence and artifacts are assembled deterministically.
LLM failure degrades to a truthful template report; it never blocks a result.
"""
from __future__ import annotations

from .config import EngineConfig
from .contracts import (
    Artifact,
    Evidence,
    GoalSpec,
    TaskContext,
    TaskReport,
    TaskStatus,
    VerificationResult,
)
from .llm import LLMClient


class ReportBuilder:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def build(
        self,
        goal: GoalSpec,
        context: TaskContext,
        status: TaskStatus,
        verification: VerificationResult,
        artifacts: list[Artifact],
        actions_summary: str,
    ) -> TaskReport:
        confidence = self._confidence(verification, context.evidence)
        narrative = self._compose_narrative(goal, context, status, verification, actions_summary)

        return TaskReport(
            executive_summary=narrative.get("executive_summary")
            or self._template_summary(goal, context, status, verification),
            key_findings=narrative.get("key_findings", []),
            evidence=list(context.evidence),
            confidence=confidence,
            sources=list(context.sources),
            artifacts=artifacts,
            next_actions=narrative.get("next_actions", []),
        )

    # ------------------------------------------------------------ internal

    def _compose_narrative(
        self,
        goal: GoalSpec,
        context: TaskContext,
        status: TaskStatus,
        verification: VerificationResult,
        actions_summary: str,
    ) -> dict:
        evidence_block = "\n".join(
            f"- [{e.kind}] {e.label}: {e.value} (source: {e.source or 'screen'})"
            for e in context.evidence[:30]
        ) or "No evidence was collected."

        prompt = f"""You are writing the result report of a completed agent task for a business user.

Goal: {goal.intent}
Deliverable expected: {goal.deliverable or "not specified"}
Task status: {status.value}
Verification: {verification.reason}
Actions performed: {actions_summary or "none"}

Collected evidence (the ONLY facts you may use):
{evidence_block}

Return ONLY valid JSON:
{{
  "executive_summary": "2-3 sentences a busy executive would read: what was done, what was found, what it means",
  "key_findings": ["the most important facts, each grounded in the evidence above"],
  "next_actions": ["1-3 concrete suggested follow-ups (empty if none make sense)"]
}}

Rules:
- Use ONLY the evidence and status above. NEVER invent facts, numbers or names.
- If no evidence was collected, say so plainly.
- If the task failed or is unverified, the summary must say so honestly.
Return ONLY JSON."""

        try:
            parsed, _raw = self._llm.complete_json(prompt, self._config.planner_model, max_tokens=600)
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            "executive_summary": str(parsed.get("executive_summary", "")).strip(),
            "key_findings": [str(v) for v in (parsed.get("key_findings") or []) if str(v).strip()][:10],
            "next_actions": [str(v) for v in (parsed.get("next_actions") or []) if str(v).strip()][:3],
        }

    @staticmethod
    def _confidence(verification: VerificationResult, evidence: list[Evidence]) -> float:
        if not evidence:
            return verification.confidence
        avg_evidence = sum(e.confidence for e in evidence) / len(evidence)
        return round((verification.confidence + avg_evidence) / 2, 3)

    @staticmethod
    def _template_summary(
        goal: GoalSpec, context: TaskContext, status: TaskStatus, verification: VerificationResult
    ) -> str:
        parts = [f"Task {status.value}: {goal.intent}."]
        if context.evidence:
            sample = "; ".join(f"{e.label}: {e.value[:80]}" for e in context.evidence[:3])
            parts.append(f"Collected {len(context.evidence)} evidence item(s): {sample}.")
        else:
            parts.append("No evidence was collected.")
        parts.append(verification.reason + ".")
        return " ".join(parts)
