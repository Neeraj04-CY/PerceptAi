"""Workforce Intelligence — the workforce observing itself.

Deterministic analysis over the measured record (sessions, approvals,
business memory, attention). Produces typed FINDINGS a manager reviews to
see how the workforce is evolving: what it is good at, where it struggles,
where humans still intervene, what repetitive work should become a standing
role, which approvals have gone stale, and which observed lessons deserve
to become permanent policy.

Rules of the moat:
- Every finding derives ONLY from measured rows — no LLM anywhere in this
  module, no invented insights, no fabricated ROI.
- Insufficient evidence is stated honestly (`coverage` + per-category
  minimums), never papered over.
- Findings carry their evidence (counts, ids, rates) so any claim can be
  audited from the same tables it came from.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import memory_service

# Minimum evidence before a category speaks at all.
MIN_RUNS_FOR_STRENGTH = 5
MIN_RUNS_FOR_STRUGGLE = 3
MIN_ADHOC_REPEATS = 3
MIN_POLICY_REINFORCEMENT = 3
ANALYSIS_DAYS = 30


def _cutoff_iso(days: int = ANALYSIS_DAYS) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _finding(kind: str, severity: str, headline: str, detail: str,
             evidence: Optional[dict] = None) -> dict:
    return {"kind": kind, "severity": severity, "headline": headline,
            "detail": detail, "evidence": evidence or {}}


def briefing(db, org_id: str) -> dict:
    """The workforce's self-review for this organization. Shape:
    {coverage: {...}, findings: [...]}, findings ordered most-actionable
    first (high, medium, info)."""
    cutoff = _cutoff_iso()
    try:
        rows = db.table("sessions").select(
            "id,workflow_id,status,execution_time,instruction,result,created_at"
        ).eq("org_id", org_id).order("created_at", desc=True).limit(500).execute().data or []
    except Exception as e:
        # Older databases predate the platform columns (002+). Honest
        # degraded answer, same contract as every platform surface.
        return {
            "period_days": ANALYSIS_DAYS,
            "coverage": {
                "operations_analyzed": 0,
                "sufficient": False,
                "note": ("The operational schema on this database is incomplete — "
                         f"apply api/migrations in order to enable Workforce "
                         f"Intelligence ({e})."),
            },
            "findings": [],
        }
    sessions = [r for r in rows if str(r.get("created_at") or "") >= cutoff
                and r.get("status") in ("completed", "unverified", "failed")]

    findings: list[dict] = []
    findings += _workflow_findings(sessions)
    findings += _adhoc_repetition(sessions)
    findings += _intervention_findings(db, org_id, sessions)
    findings += _approval_friction(db, org_id)
    findings += _policy_candidates(db, org_id)

    rank = {"high": 0, "medium": 1, "info": 2}
    findings.sort(key=lambda f: rank.get(f["severity"], 3))
    return {
        "period_days": ANALYSIS_DAYS,
        "coverage": {
            "operations_analyzed": len(sessions),
            "sufficient": len(sessions) >= MIN_RUNS_FOR_STRUGGLE,
            "note": ("" if len(sessions) >= MIN_RUNS_FOR_STRUGGLE else
                     "Not enough finished operations in the period to observe "
                     "the workforce honestly — findings will appear as real "
                     "work accumulates."),
        },
        "findings": findings,
    }


# ------------------------------------------------- per-workflow evidence

def _workflow_findings(sessions: list[dict]) -> list[dict]:
    by_wf: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s.get("workflow_id"):
            by_wf[s["workflow_id"]].append(s)

    findings: list[dict] = []
    for wf_id, runs in by_wf.items():
        n = len(runs)
        verified = sum(1 for r in runs if r.get("status") == "completed")
        troubled = sum(1 for r in runs if r.get("status") in ("failed", "unverified"))
        name = _label(runs)
        if n >= MIN_RUNS_FOR_STRENGTH and verified / n >= 0.9:
            findings.append(_finding(
                "strength", "info",
                f"{name} is a proven strength",
                f"{verified} of {n} recent runs finished with verified evidence "
                f"({round(100 * verified / n)}%). This responsibility is earning autonomy.",
                {"workflow_id": wf_id, "runs": n, "verified": verified},
            ))
        elif n >= MIN_RUNS_FOR_STRUGGLE and troubled / n >= 0.4:
            top_failure = _top_failure(runs)
            findings.append(_finding(
                "struggle", "high",
                f"{name} is struggling",
                f"{troubled} of {n} recent runs failed or needed review"
                + (f" — most common obstacle: {top_failure}" if top_failure else "")
                + ". Review its record and teach a correction if a human knows the fix.",
                {"workflow_id": wf_id, "runs": n, "troubled": troubled,
                 "top_failure": top_failure},
            ))
    return findings


def _label(runs: list[dict]) -> str:
    text = str(runs[0].get("instruction") or "This responsibility")
    return (text[:60] + "…") if len(text) > 60 else text


def _top_failure(runs: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in runs:
        result = r.get("result") or {}
        ft = str((result or {}).get("failure_type") or "").strip()
        if ft:
            counts[ft.replace("_", " ")] += 1
    return max(counts, key=counts.get) if counts else ""


# ------------------------------------------------- repetitive ad-hoc work

_NORMALIZE = re.compile(r"[\d\W_]+")


def _adhoc_repetition(sessions: list[dict]) -> list[dict]:
    """Near-identical instructions run repeatedly WITHOUT a workflow are
    unpaid automation: the same brief typed by hand. Recommend hiring a
    standing role for it."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s.get("workflow_id"):
            continue
        key = " ".join(_NORMALIZE.sub(" ", str(s.get("instruction") or "").lower()).split()[:8])
        if len(key) >= 12:
            groups[key].append(s)

    findings = []
    for _key, runs in groups.items():
        if len(runs) < MIN_ADHOC_REPEATS:
            continue
        sample = str(runs[0].get("instruction") or "")[:70]
        findings.append(_finding(
            "automation_opportunity", "medium",
            "The same brief keeps being typed by hand",
            f"“{sample}” has been briefed ad hoc {len(runs)} times this month. "
            f"Make it a standing role: it gains a track record, earns autonomy, "
            f"and can be scheduled.",
            {"occurrences": len(runs), "sample": sample,
             "session_ids": [r["id"] for r in runs[:5]]},
        ))
    return findings


# ------------------------------------------------- human intervention

def _intervention_findings(db, org_id: str, sessions: list[dict]) -> list[dict]:
    n = len(sessions)
    if n < MIN_RUNS_FOR_STRUGGLE:
        return []
    review = sum(1 for s in sessions if s.get("status") == "unverified")
    findings = []
    if review / n >= 0.3:
        findings.append(_finding(
            "intervention", "medium",
            "Humans are reviewing a large share of finished work",
            f"{review} of {n} operations ({round(100 * review / n)}%) finished without "
            f"full verification and asked for a human glance. The most common causes "
            f"are on the Knowledge page — teaching corrections shrinks this number.",
            {"needing_review": review, "operations": n},
        ))
    try:
        open_items = db.table("attention_items").select("id,kind").eq(
            "org_id", org_id).eq("status", "open").limit(100).execute().data or []
    except Exception:
        open_items = []
    if len(open_items) >= 5:
        findings.append(_finding(
            "intervention", "high",
            f"{len(open_items)} items are waiting on a human",
            "The attention queue is accumulating — unhandled failures and blocked "
            "schedules erode the time the workforce is saving.",
            {"open_attention": len(open_items)},
        ))
    return findings


# ------------------------------------------------- approvals + policy

def _approval_friction(db, org_id: str) -> list[dict]:
    try:
        insights = memory_service.approval_insights(db, org_id)
    except Exception:
        return []
    return [
        _finding("approval_friction", "medium",
                 f"Approvals for '{i['capability']}' look unnecessary",
                 i["recommendation"],
                 {"capability": i["capability"],
                  "consecutive_approvals": i["consecutive_approvals"],
                  "workspace_id": i["workspace_id"]})
        for i in insights[:3]
    ]


def _policy_candidates(db, org_id: str) -> list[dict]:
    """Observed lessons the workforce keeps re-learning deserve to become
    permanent, human-confirmed policy."""
    try:
        lessons = memory_service.list_memory(db, org_id, limit=200)
    except Exception:
        return []
    findings = []
    for lesson in lessons:
        if (lesson.get("source") == "observed"
                and int(lesson.get("times_reinforced") or 1) >= MIN_POLICY_REINFORCEMENT):
            findings.append(_finding(
                "policy_candidate", "info",
                "A learned lesson deserves to become policy",
                f"“{lesson.get('lesson', '')}” has been re-learned "
                f"{lesson.get('times_reinforced')}× from real runs. Confirm it once "
                f"(teach it) and it becomes authoritative organizational policy.",
                {"memory_id": lesson.get("id"),
                 "times_reinforced": lesson.get("times_reinforced"),
                 "scope": lesson.get("scope")},
            ))
    return findings[:3]
