"""Workflow Assurance — the measured, verified reliability of one workflow.

This is the number an enterprise buyer actually needs before deploying
autonomous automation at scale, and the one no competitor can honestly
produce. Two facts make it possible, and both are structural to PerceptAI:

  * VERIFIED outcomes. A run is "successful" only when the runtime verified
    the business outcome against real state (status COMPLETED). RPA counts "the
    script didn't throw"; we count "the invoice was actually posted." So this
    success rate means something a CIO can sign against.

  * CALIBRATED confidence. Each run reports a confidence, and we already know
    whether it was right. The calibration error (mean |confidence - outcome|,
    the same metric evals/reasoning_bench.py measures) says whether the agent
    KNOWS when it's unsure — the difference between honest autonomy and a
    confident liar.

From those, `compute_assurance` derives an evidence-backed AUTONOMY verdict:
has this workflow earned the right to run unattended, or does it still need a
human in the loop — and exactly what would change that. The verdict is a pure,
deterministic policy over the measured history, so it is auditable and testable.

Pure over a list of session rows (the sessions the plane already persists,
linked by workflow_id). No new data, no parallel system.
"""
from __future__ import annotations

from typing import Any, Optional

# Terminal statuses — the only runs that carry a verdict about the world.
COMPLETED = "completed"     # verification confirmed the business outcome
UNVERIFIED = "unverified"   # steps ran, outcome could not be confirmed
FAILED = "failed"           # did not complete
TERMINAL = (COMPLETED, UNVERIFIED, FAILED)

# Autonomy tiers, earned by measured evidence (never a checkbox).
READY = "ready"             # earned unattended operation
SUPERVISED = "supervised"   # promising; keep a human reviewing
IN_THE_LOOP = "in_the_loop"  # not yet — needs approval on every run
INSUFFICIENT = "insufficient"  # too little history to say anything honest

# The bar for each tier. Deliberately conservative: autonomy is earned.
MIN_RUNS_FOR_A_VERDICT = 5
READY_MIN_RUNS = 20
READY_MIN_VERIFIED = 0.90
READY_MAX_CALIBRATION_ERROR = 0.15
SUPERVISED_MIN_RUNS = 8
SUPERVISED_MIN_VERIFIED = 0.75


def _reported_confidence(session: dict[str, Any]) -> Optional[float]:
    """The confidence the run reported about itself — from the verification
    judgement first, then the report. None if the run never reported one."""
    result = session.get("result") or {}
    if not isinstance(result, dict):
        return None
    verification = result.get("verification") or {}
    if isinstance(verification, dict) and verification.get("confidence") is not None:
        try:
            return float(verification["confidence"])
        except (TypeError, ValueError):
            pass
    report = result.get("report") or {}
    if isinstance(report, dict) and report.get("confidence") is not None:
        try:
            return float(report["confidence"])
        except (TypeError, ValueError):
            pass
    return None


def _failure_type(session: dict[str, Any]) -> str:
    """Why a non-completed run ended, for the taxonomy. Prefer the runtime's
    typed failure_type; fall back to a coarse bucket from the error text."""
    result = session.get("result") or {}
    if isinstance(result, dict) and result.get("failure_type"):
        return str(result["failure_type"])
    error = (session.get("error") or "").lower()
    if not error:
        return "unverified" if session.get("status") == UNVERIFIED else "unknown"
    for needle, bucket in (
        # Order matters: more specific first. "loaded" would also match the
        # generic "screen" bucket, so loading is checked before it.
        ("lock", "desktop_unavailable"),
        ("load", "loading"),
        ("not found", "element_not_found"),
        ("focus", "focus_lost"),
        ("timeout", "timeout"),
        ("approval", "approval_denied"),
        ("secret", "secret_field"),
        ("duplicate", "runner_disconnect"),
        ("screen", "desktop_unavailable"),
    ):
        if needle in error:
            return bucket
    return "other"


def _autonomy(sample: int, verified_rate: float,
              calibration_error: Optional[float]) -> dict[str, Any]:
    """The evidence-backed autonomy verdict — ONE deterministic policy, tested.

    Every verdict states the reason and what would change it, so an operator is
    never asked to trust a bare label."""
    if sample < MIN_RUNS_FOR_A_VERDICT:
        return {"tier": INSUFFICIENT,
                "headline": "Not enough history yet",
                "reason": f"Only {sample} verified run(s). A trustworthy verdict "
                          f"needs at least {MIN_RUNS_FOR_A_VERDICT}.",
                "next": f"Run it {MIN_RUNS_FOR_A_VERDICT - sample} more time(s) — "
                        "supervised — to build evidence."}

    well_calibrated = calibration_error is None or calibration_error <= READY_MAX_CALIBRATION_ERROR
    if (sample >= READY_MIN_RUNS and verified_rate >= READY_MIN_VERIFIED and well_calibrated):
        return {"tier": READY,
                "headline": "Earned unattended operation",
                "reason": f"{_pct(verified_rate)} verified success over {sample} runs, "
                          f"and its confidence is well-calibrated. It knows when it's right.",
                "next": "Safe to schedule unattended. PerceptAI will still flag risks "
                        "and reach a human through the Attention inbox."}

    if sample >= SUPERVISED_MIN_RUNS and verified_rate >= SUPERVISED_MIN_VERIFIED:
        gaps = []
        if sample < READY_MIN_RUNS:
            gaps.append(f"{READY_MIN_RUNS - sample} more clean runs")
        if verified_rate < READY_MIN_VERIFIED:
            gaps.append(f"verified success above {_pct(READY_MIN_VERIFIED)}")
        if not well_calibrated:
            gaps.append("tighter confidence calibration")
        return {"tier": SUPERVISED,
                "headline": "Ready for supervised autonomy",
                "reason": f"{_pct(verified_rate)} verified success over {sample} runs — "
                          "strong, but not yet at the unattended bar.",
                "next": "Schedule it with a reviewer watching. To earn unattended "
                        "operation: " + ", ".join(gaps) + "."}

    return {"tier": IN_THE_LOOP,
            "headline": "Keep a human in the loop",
            "reason": f"{_pct(verified_rate)} verified success over {sample} runs is "
                      "below the bar for autonomy.",
            "next": "Run it attended and review the failure taxonomy below before "
                    "trusting it unattended."}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def compute_assurance(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The full assurance ledger for a workflow, from its persisted runs."""
    terminal = [s for s in sessions if s.get("status") in TERMINAL]
    sample = len(terminal)
    completed = [s for s in terminal if s.get("status") == COMPLETED]
    verified_rate = (len(completed) / sample) if sample else 0.0

    # Calibration: mean |reported confidence - actual outcome| over runs that
    # reported a confidence. outcome = 1 if verified-complete else 0.
    errors = []
    for s in terminal:
        conf = _reported_confidence(s)
        if conf is None:
            continue
        outcome = 1.0 if s.get("status") == COMPLETED else 0.0
        errors.append(abs(conf - outcome))
    calibration_error = round(sum(errors) / len(errors), 3) if errors else None

    # Failure taxonomy over the non-completed terminal runs.
    taxonomy: dict[str, int] = {}
    for s in terminal:
        if s.get("status") == COMPLETED:
            continue
        taxonomy[_failure_type(s)] = taxonomy.get(_failure_type(s), 0) + 1
    taxonomy_sorted = sorted(
        ({"type": k, "count": v} for k, v in taxonomy.items()),
        key=lambda t: t["count"], reverse=True)

    durations = [float(s["execution_time"]) for s in terminal
                 if s.get("execution_time") is not None]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    return {
        "sample_size": sample,
        "verified_success_rate": round(verified_rate, 3),
        "completed": len(completed),
        "unverified": sum(1 for s in terminal if s.get("status") == UNVERIFIED),
        "failed": sum(1 for s in terminal if s.get("status") == FAILED),
        "calibration_error": calibration_error,
        "calibration_samples": len(errors),
        "avg_duration_s": avg_duration,
        "failure_taxonomy": taxonomy_sorted,
        "autonomy": _autonomy(sample, verified_rate, calibration_error),
    }


# A workflow is a "confident liar" when it succeeds often but its confidence
# does NOT track reality — the exact thing a fleet operator must never trust
# unattended, and the exact thing only PerceptAI can see.
CONFIDENT_LIAR_MIN_SUCCESS = 0.85
CONFIDENT_LIAR_MIN_CALIBRATION_ERROR = 0.20


def fleet_posture(workflows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-workflow assurance into the org's AUTONOMY POSTURE — the single
    trust reading a Head of Automation watches all day: how much of the
    autonomous workforce has earned the right to run itself, how much still
    needs a human, and which workflows look reliable but can't be trusted.

    Input: a list of {"id", "name", "sessions": [...]} — the published task
    workflows and their persisted runs. Pure, so it is unit-tested.
    """
    by_tier: dict[str, int] = {READY: 0, SUPERVISED: 0, IN_THE_LOOP: 0, INSUFFICIENT: 0}
    total_runs = 0
    weighted_success = 0.0
    liars: list[dict[str, Any]] = []
    workflow_cards: list[dict[str, Any]] = []

    for wf in workflows:
        a = compute_assurance(wf.get("sessions") or [])
        tier = a["autonomy"]["tier"]
        by_tier[tier] = by_tier.get(tier, 0) + 1
        total_runs += a["sample_size"]
        weighted_success += a["verified_success_rate"] * a["sample_size"]

        card = {
            "id": wf.get("id"), "name": wf.get("name", ""),
            "tier": tier,
            "verified_success_rate": a["verified_success_rate"],
            "sample_size": a["sample_size"],
            "calibration_error": a["calibration_error"],
        }
        workflow_cards.append(card)

        ce = a["calibration_error"]
        if (a["sample_size"] >= MIN_RUNS_FOR_A_VERDICT
                and a["verified_success_rate"] >= CONFIDENT_LIAR_MIN_SUCCESS
                and ce is not None and ce >= CONFIDENT_LIAR_MIN_CALIBRATION_ERROR):
            liars.append(card)

    graded = by_tier[READY] + by_tier[SUPERVISED] + by_tier[IN_THE_LOOP]
    workflow_cards.sort(key=lambda c: (_TIER_ORDER.get(c["tier"], 9),
                                       -c["verified_success_rate"]))
    return {
        "total_workflows": len(workflows),
        "graded_workflows": graded,
        "by_tier": by_tier,
        "earned_autonomy": by_tier[READY],
        "total_runs": total_runs,
        "fleet_verified_success_rate": round(weighted_success / total_runs, 3) if total_runs else None,
        "confident_liars": liars,
        "workflows": workflow_cards,
    }


# Worst-first ordering so the operator sees what needs attention at the top.
_TIER_ORDER = {IN_THE_LOOP: 0, SUPERVISED: 1, INSUFFICIENT: 2, READY: 3}
