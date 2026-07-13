"""The Organizational Graph (Milestone D) — discoveries from measured
relationships, pinned. Deterministic, evidence-carrying, honest when the
evidence is thin, degrades on old schemas."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import org_graph  # noqa: E402
from tests.supafake import FakeSupabase

ORG = "org-1"


def _now(days_ago: float = 1.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _workflow(db, wf_id: str, name: str, instruction: str = ""):
    db.table("workflows").insert({
        "id": wf_id, "org_id": ORG, "name": name,
        "instruction": instruction or name, "status": "published",
    }).execute()


def _run(db, wf_id: str | None, status: str, failure_type: str = "",
         instruction: str = "run"):
    db.table("sessions").insert({
        "id": f"s-{len(db.rows['sessions'])}", "org_id": ORG,
        "workflow_id": wf_id, "status": status, "instruction": instruction,
        "created_at": _now(),
        "result": {"failure_type": failure_type} if failure_type else {},
    }).execute()


def test_graph_connects_workflows_departments_and_applications():
    db = FakeSupabase()
    _workflow(db, "wf-1", "Post invoice to the ERP")  # finance template lineage
    for _ in range(3):
        _run(db, "wf-1", "completed")
    g = org_graph.build_graph(db, ORG)
    types = {n["type"] for n in g["nodes"]}
    assert {"workflow", "department", "application"} <= types
    rels = {e["rel"] for e in g["edges"]}
    assert {"BELONGS_TO", "TOUCHES"} <= rels
    wf = next(n for n in g["nodes"] if n["type"] == "workflow")
    assert wf["runs"] == 3 and wf["verified_rate"] == 1.0


def test_duplicated_work_is_discovered_across_workflows():
    db = FakeSupabase()
    _workflow(db, "wf-a", "Post invoice to the ERP",
              "In SAP, create and post a vendor invoice for vendor ACME and report the number")
    _workflow(db, "wf-b", "Invoice posting (procurement copy)",
              "In SAP, create and post a vendor invoice for vendor ACME and report the doc number")
    out = org_graph.discoveries(db, ORG)
    dups = [d for d in out["discoveries"] if d["kind"] == "duplicated_work"]
    assert dups and dups[0]["evidence"]["similarity"] >= 0.78
    assert set(dups[0]["evidence"]["workflow_ids"]) == {"wf-a", "wf-b"}
    # Unrelated briefs stay silent.
    db2 = FakeSupabase()
    _workflow(db2, "wf-a", "Post invoice to the ERP", "In SAP, post vendor invoices and verify")
    _workflow(db2, "wf-b", "Triage a support ticket across apps",
              "Read the Zendesk ticket, check the CRM and billing, summarize")
    assert [d for d in org_graph.discoveries(db2, ORG)["discoveries"]
            if d["kind"] == "duplicated_work"] == []


def test_systemic_obstacle_names_the_shared_application():
    db = FakeSupabase()
    _workflow(db, "wf-1", "Post invoice to the ERP")          # touches sap
    _workflow(db, "wf-2", "SAP vendor audit", "In SAP, audit the vendor records")
    for _ in range(2):
        _run(db, "wf-1", "failed", failure_type="modal_dialog")
        _run(db, "wf-2", "failed", failure_type="modal_dialog")
    _run(db, "wf-1", "completed")
    out = org_graph.discoveries(db, ORG)
    sys_ = [d for d in out["discoveries"] if d["kind"] == "systemic_obstacle"]
    assert sys_ and sys_[0]["severity"] == "high"
    assert sys_[0]["evidence"]["workflows"] == 2
    assert sys_[0]["evidence"]["occurrences"] == 4
    assert sys_[0]["evidence"]["application"] == "sap"
    assert sys_[0]["recommended_action"]
    # One struggling workflow alone is not systemic.
    db2 = FakeSupabase()
    _workflow(db2, "wf-1", "Post invoice to the ERP")
    _run(db2, "wf-1", "failed", failure_type="modal_dialog")
    assert [d for d in org_graph.discoveries(db2, ORG)["discoveries"]
            if d["kind"] == "systemic_obstacle"] == []


def test_learning_transfer_gap_on_a_shared_application():
    db = FakeSupabase()
    _workflow(db, "wf-good", "Update a CRM opportunity")   # salesforce lineage
    _workflow(db, "wf-bad", "Salesforce case sweep", "In Salesforce, sweep open cases")
    for _ in range(4):
        _run(db, "wf-good", "completed")
    for _ in range(3):
        _run(db, "wf-bad", "failed")
    _run(db, "wf-bad", "completed")
    out = org_graph.discoveries(db, ORG)
    xfer = [d for d in out["discoveries"] if d["kind"] == "learning_transfer"]
    assert xfer
    assert xfer[0]["evidence"]["best"]["verified_rate"] == 1.0
    assert xfer[0]["evidence"]["worst"]["verified_rate"] == 0.25
    assert "teach" in xfer[0]["recommended_action"].lower()
    # A small gap is not a discovery.
    db2 = FakeSupabase()
    _workflow(db2, "wf-1", "Update a CRM opportunity")
    _workflow(db2, "wf-2", "Salesforce case sweep", "In Salesforce, sweep cases")
    for _ in range(4):
        _run(db2, "wf-1", "completed")
        _run(db2, "wf-2", "completed")
    assert [d for d in org_graph.discoveries(db2, ORG)["discoveries"]
            if d["kind"] == "learning_transfer"] == []


def test_redundant_approvals_require_breadth_and_zero_denials():
    db = FakeSupabase()
    for i in range(7):
        db.table("approvals").insert({
            "org_id": ORG, "capability": "erp_write", "status": "approved",
            "workspace_id": f"ws-{i % 2}", "created_at": _now(),
        }).execute()
    out = org_graph.discoveries(db, ORG)
    red = [d for d in out["discoveries"] if d["kind"] == "redundant_approvals"]
    assert red and red[0]["evidence"]["approved"] == 7
    # One denial means judgment IS being exercised.
    db.table("approvals").insert({
        "org_id": ORG, "capability": "erp_write", "status": "denied",
        "workspace_id": "ws-0", "created_at": _now(),
    }).execute()
    assert [d for d in org_graph.discoveries(db, ORG)["discoveries"]
            if d["kind"] == "redundant_approvals"] == []


def test_every_discovery_carries_the_full_contract():
    db = FakeSupabase()
    _workflow(db, "wf-1", "Post invoice to the ERP")
    _workflow(db, "wf-2", "SAP vendor audit", "In SAP, audit the vendor records")
    for _ in range(2):
        _run(db, "wf-1", "failed", failure_type="loading")
        _run(db, "wf-2", "failed", failure_type="loading")
    out = org_graph.discoveries(db, ORG)
    assert out["discoveries"]
    for d in out["discoveries"]:
        assert {"kind", "severity", "headline", "detail", "evidence", "confidence",
                "affected_departments", "business_impact",
                "recommended_action"} <= set(d)
        assert 0.0 < d["confidence"] < 1.0


def test_discoveries_are_deterministic():
    def build():
        db = FakeSupabase()
        _workflow(db, "wf-1", "Post invoice to the ERP")
        _workflow(db, "wf-2", "SAP vendor audit", "In SAP, audit the vendors")
        for _ in range(2):
            _run(db, "wf-1", "failed", failure_type="modal_dialog")
            _run(db, "wf-2", "failed", failure_type="modal_dialog")
        return org_graph.discoveries(db, ORG)["discoveries"]
    assert build() == build()


def test_old_schema_degrades_honestly():
    class _OldDb:
        def table(self, name):
            raise RuntimeError("column sessions.workflow_id does not exist")
    out = org_graph.discoveries(_OldDb(), ORG)
    assert out["discoveries"] == []
    assert not out["coverage"]["sufficient"]
    assert "verify_schema" in out["coverage"]["note"]
