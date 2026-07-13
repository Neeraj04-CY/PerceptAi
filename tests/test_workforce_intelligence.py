"""Workforce Intelligence (Milestone C3) — the self-observing workforce.

Every finding derives from measured rows; insufficient evidence is stated
honestly; no category invents anything."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import intelligence  # noqa: E402
import memory_service  # noqa: E402
from tests.supafake import FakeSupabase

ORG = "org-1"


def _now(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _session(db, *, wf: str | None, status: str, instruction: str,
             days_ago: float = 1.0, failure_type: str = ""):
    db.table("sessions").insert({
        "id": f"s-{len(db.rows['sessions'])}", "org_id": ORG, "workflow_id": wf,
        "status": status, "instruction": instruction,
        "execution_time": 20.0, "created_at": _now(days_ago),
        "result": {"failure_type": failure_type} if failure_type else {},
    }).execute()


def test_insufficient_history_is_stated_honestly():
    db = FakeSupabase()
    out = intelligence.briefing(db, ORG)
    assert out["coverage"]["operations_analyzed"] == 0
    assert not out["coverage"]["sufficient"]
    assert "Not enough" in out["coverage"]["note"]
    assert out["findings"] == []


def test_strength_requires_a_real_track_record():
    db = FakeSupabase()
    for _ in range(6):
        _session(db, wf="wf-1", status="completed", instruction="Post invoice to the ERP")
    out = intelligence.briefing(db, ORG)
    strengths = [f for f in out["findings"] if f["kind"] == "strength"]
    assert strengths and strengths[0]["evidence"]["runs"] == 6
    # Four verified runs are NOT enough to claim a strength.
    db2 = FakeSupabase()
    for _ in range(4):
        _session(db2, wf="wf-1", status="completed", instruction="Post invoice")
    assert [f for f in intelligence.briefing(db2, ORG)["findings"]
            if f["kind"] == "strength"] == []


def test_struggles_name_the_measured_obstacle():
    db = FakeSupabase()
    _session(db, wf="wf-2", status="failed", instruction="Reconcile batch",
             failure_type="modal_dialog")
    _session(db, wf="wf-2", status="failed", instruction="Reconcile batch",
             failure_type="modal_dialog")
    _session(db, wf="wf-2", status="completed", instruction="Reconcile batch")
    out = intelligence.briefing(db, ORG)
    struggles = [f for f in out["findings"] if f["kind"] == "struggle"]
    assert struggles and struggles[0]["severity"] == "high"
    assert struggles[0]["evidence"]["top_failure"] == "modal dialog"


def test_repeated_adhoc_briefs_become_automation_opportunities():
    db = FakeSupabase()
    for i in range(4):
        _session(db, wf=None, status="completed",
                 instruction=f"Reconcile payment batch B-{80 + i} between ERP and bank")
    out = intelligence.briefing(db, ORG)
    ops = [f for f in out["findings"] if f["kind"] == "automation_opportunity"]
    assert ops and ops[0]["evidence"]["occurrences"] == 4
    # Two occurrences stay quiet.
    db2 = FakeSupabase()
    for i in range(2):
        _session(db2, wf=None, status="completed", instruction="Audit the CRM records")
    assert [f for f in intelligence.briefing(db2, ORG)["findings"]
            if f["kind"] == "automation_opportunity"] == []


def test_reinforced_observed_lessons_become_policy_candidates():
    db = FakeSupabase()
    for _ in range(3):
        _session(db, wf="wf-1", status="completed", instruction="anything at all")
    for s in ("s1", "s2", "s3"):
        memory_service.record(
            db, ORG, kind="recovery", subject="SAP",
            lesson="In SAP, modal dialog can block progress; recovery that worked: ESC",
            source="observed", scope="app:sap", evidence_ref={"session_id": s})
    out = intelligence.briefing(db, ORG)
    cands = [f for f in out["findings"] if f["kind"] == "policy_candidate"]
    assert cands and cands[0]["evidence"]["times_reinforced"] == 3


def test_taught_lessons_are_not_renominated_as_policy():
    db = FakeSupabase()
    for _ in range(3):
        _session(db, wf="wf-1", status="completed", instruction="anything")
    memory_service.teach(db, ORG, "u", subject="x", lesson="already policy")
    out = intelligence.briefing(db, ORG)
    assert [f for f in out["findings"] if f["kind"] == "policy_candidate"] == []


def test_findings_rank_most_actionable_first():
    db = FakeSupabase()
    for _ in range(6):
        _session(db, wf="wf-1", status="completed", instruction="Post invoice")
    _session(db, wf="wf-2", status="failed", instruction="Reconcile", failure_type="loading")
    _session(db, wf="wf-2", status="failed", instruction="Reconcile", failure_type="loading")
    _session(db, wf="wf-2", status="unverified", instruction="Reconcile")
    out = intelligence.briefing(db, ORG)
    severities = [f["severity"] for f in out["findings"]]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s])


def test_incomplete_schema_degrades_honestly_never_500s():
    """Live databases that predate the platform columns get an honest
    coverage note, not an exception — the same contract as every other
    platform surface."""
    class _OldDb:
        def table(self, name):
            raise RuntimeError("column sessions.workflow_id does not exist")
    out = intelligence.briefing(_OldDb(), ORG)
    assert out["findings"] == []
    assert not out["coverage"]["sufficient"]
    assert "migrations" in out["coverage"]["note"]
