"""The Organizational Record (Phase 3, M1) — grounded search + timeline.

Deterministic term search over the tables the platform already writes;
every hit typed and linked; missing sources named, never fabricated."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import memory_service  # noqa: E402
import org_record  # noqa: E402
from tests.supafake import FakeSupabase

ORG = "org-1"


def _now(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed(db):
    memory_service.teach(db, ORG, "u", subject="SAP",
                         lesson="SAP requires three confirmations after an update",
                         kind="policy", scope="app:sap")
    db.table("workflows").insert({
        "id": "wf-1", "org_id": ORG, "name": "Post invoice to the ERP",
        "instruction": "In SAP, create and post a vendor invoice",
        "status": "published", "updated_at": _now(2)}).execute()
    db.table("sessions").insert({
        "id": "s-1", "org_id": ORG, "workflow_id": "wf-1",
        "instruction": "Post invoice INV-4471 in SAP", "status": "failed",
        "created_at": _now(1), "result": {"failure_type": "modal_dialog"}}).execute()
    db.table("approvals").insert({
        "id": "ap-1", "org_id": ORG, "capability": "erp_write",
        "objective": "Post a $12,400 invoice in SAP", "status": "approved",
        "reason": "", "created_at": _now(0.5)}).execute()


def test_search_answers_what_affects_an_application():
    db = FakeSupabase()
    _seed(db)
    out = org_record.search(db, ORG, "what policies affect SAP")
    types = [h["type"] for h in out["hits"]]
    assert "lesson" in types and "workflow" in types and "operation" in types
    lesson = next(h for h in out["hits"] if h["type"] == "lesson")
    assert "three confirmations" in lesson["snippet"]
    assert all("ref" in h for h in out["hits"])       # every hit links back


def test_title_matches_outrank_body_matches():
    db = FakeSupabase()
    _seed(db)
    out = org_record.search(db, ORG, "invoice")
    assert out["hits"][0]["type"] in ("workflow", "operation")
    assert out["hits"][0]["relevance"] >= out["hits"][-1]["relevance"]


def test_search_finds_who_approved_a_capability():
    db = FakeSupabase()
    _seed(db)
    out = org_record.search(db, ORG, "erp_write approval")
    approval = next(h for h in out["hits"] if h["type"] == "approval")
    assert approval["status"] == "approved"


def test_missing_sources_are_named_never_fabricated():
    class _PartialDb(FakeSupabase):
        def table(self, name):
            if name in ("attention_items", "audit_log", "business_memory"):
                raise RuntimeError(f"table {name} missing")
            return super().table(name)
    db = _PartialDb()
    db.table("workflows").insert({
        "id": "wf-1", "org_id": ORG, "name": "Post invoice to the ERP",
        "instruction": "In SAP, post invoices", "status": "published",
        "updated_at": _now()}).execute()
    out = org_record.search(db, ORG, "invoice")
    assert out["hits"] and out["hits"][0]["type"] == "workflow"
    assert set(out["sources_skipped"]) == {"attention", "audit", "lessons"}
    assert "verify_schema" in out["note"]


def test_empty_query_is_answered_honestly():
    out = org_record.search(FakeSupabase(), ORG, "the of and")
    assert out["hits"] == [] and "meaningful word" in out["note"]


def test_timeline_merges_everything_newest_first():
    db = FakeSupabase()
    _seed(db)
    out = org_record.timeline(db, ORG, limit=10)
    whens = [e["when"] for e in out["entries"]]
    assert whens == sorted(whens, reverse=True)
    types = {e["type"] for e in out["entries"]}
    assert {"lesson", "workflow", "operation", "approval"} <= types
