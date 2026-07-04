"""Hypothesis generation: multiple explanations, kept alive until disproven.

When a step fails (or the world surprises us), the agent never assumes
the first explanation. Deterministic candidates are read directly from
the evidence — what changed since the failure, what the error says, what
the world looks like — and merged with the LLM diagnosis (the healer's
ranked alternatives). Each hypothesis carries its own probability and,
when one exists, a SAFE generic recovery. Recovery steps are never
app-specific and never blind: a hypothesis without a grounded recovery
simply has none.

Pure logic, deterministic, no LLM calls (the healer owns the LLM side).
"""
from __future__ import annotations

import uuid
from typing import Optional

from .config import EngineConfig
from .contracts import (
    ActionType,
    HealingPlan,
    Hypothesis,
    Step,
    WorldDiff,
    WorldState,
    utc_now_iso,
)
from .fusion import normalize_text, text_similarity

# Window-title fragments that usually mean a blocking surface appeared.
_DIALOG_MARKERS = ("dialog", "alert", "confirm", "warning", "error", "sign in", "login", "permission")


class HypothesisGenerator:
    def __init__(self, config: EngineConfig):
        self._config = config

    def generate(self, failed_step: Step, error: str,
                 world: Optional[WorldState], diff: Optional[WorldDiff],
                 expected_window: str = "") -> list[Hypothesis]:
        """Candidate explanations for a failure, from signals alone."""
        subject = f"{failed_step.action.value} '{failed_step.description}' failed"
        candidates: list[Hypothesis] = []

        def add(kind: str, explanation: str, probability: float,
                evidence: str, steps: Optional[list[Step]] = None) -> None:
            candidates.append(Hypothesis(
                id=str(uuid.uuid4())[:8], subject=subject, explanation=explanation,
                kind=kind, probability=round(probability, 3), source="signals",
                recovery_steps=steps or [], evidence_for=[evidence],
            ))

        error_l = (error or "").lower()

        if diff is not None and diff.appeared_windows:
            blocking = [t for t in diff.appeared_windows
                        if any(m in t.lower() for m in _DIALOG_MARKERS)]
            if blocking:
                add("modal_dialog",
                    f"a dialog appeared and may be blocking the target: {blocking[0]}",
                    0.75, f"window appeared since failure: {blocking[0]}")
            else:
                add("window_changed",
                    f"a new window appeared since the failure: {diff.appeared_windows[0]}",
                    0.5, f"window appeared: {diff.appeared_windows[0]}")

        if diff is not None and diff.focus_changed:
            # Focus recovery is generic and safe: refocus what we expected.
            steps = None
            if expected_window:
                steps = [Step(
                    action=ActionType.FOCUS_WINDOW,
                    description=f"refocus {expected_window}",
                    params={"window": expected_window}, source="healer",
                )]
            add("focus_lost",
                f"keyboard focus moved to '{diff.focus_after}' during the step",
                0.65, f"focus moved from '{diff.focus_before}' to '{diff.focus_after}'",
                steps)

        if world is not None and self._looks_loading(world, diff):
            add("loading",
                "the application appears to be still loading or rendering",
                0.55, "screen is sparse or content dropped sharply since the failure",
                [Step(action=ActionType.WAIT, description="wait for the app to settle",
                      params={"wait": self._config.settle_after_launch_s}, source="healer")])

        if "cannot launch" in error_l or "not installed" in error_l or "no window" in error_l:
            add("app_not_open",
                "the target application did not open",
                0.7, f"launcher error: {error[:100]}")

        if "not found" in error_l:
            renamed = self._similar_on_screen(failed_step, world)
            if renamed:
                add("element_renamed",
                    f"the target may now be labelled '{renamed}'",
                    0.6, f"similar element visible: '{renamed}'")
            else:
                add("element_not_found",
                    "the target element is not on the current screen",
                    0.5, "no similar element visible")

        if world is not None and expected_window:
            focused = normalize_text(world.focused_window)
            expected = normalize_text(expected_window)
            if focused and expected and expected not in focused and focused not in expected:
                add("wrong_app",
                    f"the focused window is '{world.focused_window}', not the target",
                    0.6, f"expected '{expected_window}' to be focused")

        if not candidates:
            add("other", "no visible cause; the screen shows no relevant change", 0.2,
                "no diagnostic signals in the world diff")
        return sorted(candidates, key=lambda h: h.probability, reverse=True)

    def merge_llm(self, hypotheses: list[Hypothesis], plan: HealingPlan,
                  subject: str) -> list[Hypothesis]:
        """Fold the healer's ranked diagnoses into the candidate set.
        Same failure kind = same hypothesis: the LLM corroborates the
        signal (probability compounds) instead of duplicating it."""
        merged = list(hypotheses)
        for candidate in [plan, *plan.alternatives]:
            if not candidate.diagnosis:
                continue
            existing = next((h for h in merged if h.kind == candidate.failure_type), None)
            if existing is not None:
                p, c = existing.probability, max(0.0, min(1.0, candidate.confidence))
                existing.probability = round(min(0.99, p + c - p * c), 3)
                existing.evidence_for.append(f"LLM diagnosis agrees: {candidate.diagnosis}")
                if candidate.steps and not existing.recovery_steps:
                    existing.recovery_steps = candidate.steps
            else:
                merged.append(Hypothesis(
                    id=str(uuid.uuid4())[:8], subject=subject,
                    explanation=candidate.diagnosis, kind=candidate.failure_type,
                    probability=round(max(0.0, min(0.99, candidate.confidence)), 3),
                    source="llm", recovery_steps=list(candidate.steps),
                    evidence_for=[f"LLM diagnosis: {candidate.diagnosis}"],
                ))
        return sorted(merged, key=lambda h: h.probability, reverse=True)

    @staticmethod
    def resolve(hypothesis: Hypothesis, confirmed: bool, reason: str) -> Hypothesis:
        hypothesis.status = "confirmed" if confirmed else "rejected"
        hypothesis.resolved_at = utc_now_iso()
        hypothesis.resolution_reason = reason
        if confirmed:
            hypothesis.evidence_for.append(reason)
        else:
            hypothesis.evidence_against.append(reason)
        return hypothesis

    # ------------------------------------------------------------ internal

    @staticmethod
    def _looks_loading(world: WorldState, diff: Optional[WorldDiff]) -> bool:
        sparse = len(world.elements) <= 2 and bool(world.windows)
        collapsed = diff is not None and diff.elements_removed >= 8 and diff.elements_added <= 1
        return sparse or collapsed

    def _similar_on_screen(self, failed_step: Step,
                           world: Optional[WorldState]) -> str:
        """A near-match for the missing target suggests a rename, not a
        disappearance — OCR noise and dynamic labels look exactly like this."""
        query = str(failed_step.params.get("find", ""))
        if not query or world is None:
            return ""
        best_name, best_score = "", 0.0
        for el in world.elements:
            if not el.name:
                continue
            score = text_similarity(el.name, query)
            if 0.55 <= score < 1.0 and score > best_score:
                best_name, best_score = el.name, score
        return best_name
