"""Business Memory (Milestone C2) — the compounding moat, pinned.

Lessons are recorded from human teaching and measured run facts, deduped
and REINFORCED (repetition raises confidence, never noise), recalled by
deterministic term match in exactly the shape the engine's knowledge
recall consumes, and merged into planning through the OrgMemoryStore
decorator — the engine itself is unchanged (the recall→facts→planner path
is pinned by test_memory_knowledge)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import memory_service  # noqa: E402
from org_memory import OrgMemoryStore  # noqa: E402
from tests.supafake import FakeSupabase

ORG = "org-1"


def _db():
    return FakeSupabase()


# ------------------------------------------------------------- record

def test_record_then_reinforce_compounds_not_duplicates():
    db = _db()
    a = memory_service.record(db, ORG, kind="quirk", subject="SAP",
                              lesson="SAP requires three confirmations after an update",
                              source="observed", scope="app:sap",
                              evidence_ref={"session_id": "s1"})
    first_confidence = a["confidence"]  # capture: the fake stores rows by reference
    b = memory_service.record(db, ORG, kind="quirk", subject="SAP",
                              lesson="  sap requires THREE confirmations after an update ",
                              source="observed", scope="app:sap",
                              evidence_ref={"session_id": "s2"})
    rows = db.rows["business_memory"]
    assert len(rows) == 1                       # deduped by normalized lesson
    assert b["times_reinforced"] == 2
    assert b["confidence"] > first_confidence   # reinforcement compounds
    assert {"session_id": "s1"} in b["evidence"] and {"session_id": "s2"} in b["evidence"]


def test_taught_lessons_start_authoritative():
    db = _db()
    row = memory_service.teach(db, ORG, "user-9", subject="Invoices",
                               lesson="Invoices from ACME belong to vendor 400312")
    assert row["source"] == "taught"
    assert row["confidence"] >= 0.9
    assert row["taught_by"] == "user-9"


# ------------------------------------------------------------- recall

def test_recall_matches_terms_and_shapes_for_the_engine():
    db = _db()
    memory_service.teach(db, ORG, "u", subject="SAP",
                         lesson="SAP requires three confirmations after an update",
                         scope="app:sap", kind="quirk")
    rows = memory_service.recall(db, ORG, ["SAP", "invoice"])
    assert rows and rows[0]["value"].startswith("SAP requires")
    # Exactly the engine knowledge-row shape: entity/attribute/value/confidence.
    assert {"entity", "attribute", "value", "source", "confidence"} <= set(rows[0])
    assert rows[0]["source"] == "business_memory"


def test_app_scoped_lessons_propagate_across_workflows():
    """Finance learns a SAP quirk; a Procurement instruction touching SAP
    recalls it — learning compounds across the organization."""
    db = _db()
    memory_service.record(db, ORG, kind="quirk", subject="SAP",
                          lesson="SAP requires three confirmations after an update",
                          source="observed", scope="app:sap")
    rows = memory_service.recall(db, ORG, ["SAP", "purchase", "order"])
    assert rows, "app-scoped lesson must reach any run touching that app"


def test_org_policies_apply_everywhere_and_noise_does_not():
    db = _db()
    memory_service.teach(db, ORG, "u", subject="general",
                         lesson="Never post financial documents without a document number",
                         kind="policy", scope="org")
    memory_service.record(db, ORG, kind="quirk", subject="Zendesk",
                          lesson="Zendesk macros lag after login", source="observed",
                          scope="app:zendesk")
    rows = memory_service.recall(db, ORG, ["invoice", "erp"])
    values = [r["value"] for r in rows]
    assert any("document number" in v for v in values)   # org scope: always eligible
    assert all("Zendesk" not in v for v in values)       # unrelated app: excluded


# ------------------------------------------------ learn from run facts

def test_recoveries_on_the_event_stream_become_lessons():
    db = _db()
    events = [
        {"type": "world_snapshot", "payload": {"focused_window": "SAP Invoice Entry"}},
        {"type": "recovery_completed",
         "payload": {"recovered": True, "failure_type": "modal_dialog",
                     "diagnosis": "a blocking dialog was dismissed with ESC"}},
    ]
    n = memory_service.learn_from_events(db, ORG, None, "sess-1",
                                         "Post invoice INV-1 in SAP", events)
    assert n == 1
    row = db.rows["business_memory"][0]
    assert row["kind"] == "recovery" and row["source"] == "observed"
    assert "modal dialog" in row["lesson"] and "ESC" in row["lesson"]
    assert row["scope"].startswith("app:")
    assert row["evidence"] == [{"session_id": "sess-1"}]


def test_failed_recoveries_teach_nothing():
    db = _db()
    events = [{"type": "recovery_completed",
               "payload": {"recovered": False, "failure_type": "loading",
                           "diagnosis": "waited longer"}}]
    assert memory_service.learn_from_events(db, ORG, None, "s", "x", events) == 0
    assert db.rows["business_memory"] == []


# ------------------------------------------------ measured insights

def test_consecutive_approvals_become_a_standing_approval_insight():
    db = _db()
    for i in range(12):
        db.table("approvals").insert({
            "org_id": ORG, "workspace_id": "ws1", "capability": "erp_write",
            "status": "approved", "created_at": f"2026-07-{i+1:02d}T00:00:00Z",
        }).execute()
    insights = memory_service.approval_insights(db, ORG, threshold=10)
    assert insights and insights[0]["capability"] == "erp_write"
    assert insights[0]["consecutive_approvals"] == 12


def test_a_denial_breaks_the_streak():
    db = _db()
    rows = [("approved" if i != 0 else "denied") for i in range(12)]
    # newest row first by created_at desc: put the denial most recent
    for i, status in enumerate(rows):
        db.table("approvals").insert({
            "org_id": ORG, "workspace_id": "ws1", "capability": "erp_write",
            "status": status, "created_at": f"2026-07-{20-i:02d}T00:00:00Z",
        }).execute()
    assert memory_service.approval_insights(db, ORG, threshold=10) == []


# ------------------------------------------------ the engine seam

class _LocalMemory:
    def recall_knowledge(self, terms, limit=10):
        return [{"entity": "local", "attribute": "cache", "value": "local fact",
                 "source": "knowledge", "confidence": 0.5}]

    def remember_interface(self, app, elements):
        self.remembered = (app, elements)


def test_org_memory_store_merges_org_lessons_ahead_of_local():
    db = _db()
    memory_service.teach(db, ORG, "u", subject="SAP",
                         lesson="SAP requires three confirmations", scope="app:sap")
    store = OrgMemoryStore(_LocalMemory(), db, ORG)
    rows = store.recall_knowledge(["sap"])
    assert rows[0]["source"] == "business_memory"           # org lesson leads
    assert any(r["value"] == "local fact" for r in rows)    # local kept


def test_org_memory_store_survives_db_failure_and_delegates():
    class _DeadDb:
        def table(self, name):
            raise RuntimeError("db down")
    store = OrgMemoryStore(_LocalMemory(), _DeadDb(), ORG)
    rows = store.recall_knowledge(["sap"])
    assert rows and rows[0]["value"] == "local fact"        # never blocks a run
    store.remember_interface("app", [])                     # writes delegate
    assert store._base.remembered == ("app", [])
