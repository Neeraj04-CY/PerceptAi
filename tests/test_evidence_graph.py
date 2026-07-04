"""EvidenceGraph: corroboration, versions, conflicts, grounded reports."""
from perceptai.contracts import Evidence
from perceptai.workforce.evidence_graph import EvidenceGraph


def test_corroboration_compounds_confidence_noisy_or():
    graph = EvidenceGraph()
    graph.assert_claim("Stripe", "pricing", "2.9% + 30c",
                       source="stripe.com", confidence=0.6)
    claim = graph.assert_claim("Stripe", "pricing", "2.9% + 30c",
                               source="docs", confidence=0.5)
    assert claim.version == 1
    assert claim.supports == 2
    assert abs(claim.confidence - 0.8) < 1e-9  # 1 - 0.4*0.5
    assert claim.sources == ["stripe.com", "docs"]


def test_confidence_is_capped():
    graph = EvidenceGraph()
    for i in range(10):
        claim = graph.assert_claim("E", "a", "v", source=f"s{i}", confidence=0.9)
    assert claim.confidence <= 0.99


def test_different_value_creates_version_and_conflict():
    graph = EvidenceGraph()
    graph.assert_claim("Stripe", "pricing", "2.9%", source="a", confidence=0.8)
    v2 = graph.assert_claim("Stripe", "pricing", "3.4%", source="b", confidence=0.7)
    assert v2.version == 2
    conflicts = graph.conflicts()
    assert len(conflicts) == 1
    assert {v["value"] for v in conflicts[0]["values"]} == {"2.9%", "3.4%"}
    # Current claim is the newest version; history is never overwritten.
    assert graph.claim("Stripe", "pricing").value == "3.4%"


def test_low_confidence_disagreement_is_not_a_conflict():
    graph = EvidenceGraph()
    graph.assert_claim("E", "a", "x", confidence=0.9)
    graph.assert_claim("E", "a", "y", confidence=0.2)  # not credible
    assert graph.conflicts() == []


def test_ingest_maps_evidence_with_entity_hint():
    graph = EvidenceGraph()
    changed = graph.ingest(
        [Evidence(kind="price", label="monthly_price", value="$20",
                  source="site", confidence=0.8),
         Evidence(kind="text", label="", value="", source="site")],  # empty dropped
        entity="Acme",
    )
    assert changed == 1
    assert graph.claim("Acme", "monthly_price").value == "$20"


def test_relations_corroborate_too():
    graph = EvidenceGraph()
    graph.relate("Stripe", "competes_with", "Adyen", source="a", confidence=0.5)
    rel = graph.relate("stripe", "competes_with", "adyen", source="b", confidence=0.5)
    assert len(graph.relations) == 1
    assert rel.confidence > 0.5 and rel.sources == ["a", "b"]


def test_report_evidence_is_current_claims_ranked_by_confidence():
    graph = EvidenceGraph()
    graph.assert_claim("A", "attr", "low", confidence=0.3)
    graph.assert_claim("B", "attr", "high", confidence=0.9)
    evidence = graph.report_evidence()
    assert [e.value for e in evidence] == ["high", "low"]
    assert all(isinstance(e, Evidence) for e in evidence)


def test_summary_and_sources():
    graph = EvidenceGraph()
    graph.assert_claim("A", "x", "1", source="s1", confidence=0.8)
    graph.assert_claim("B", "y", "2", source="s2", confidence=0.6)
    summary = graph.summary()
    assert summary["claims"] == 2 and summary["entities"] == 2
    assert summary["conflicts"] == 0
    assert set(graph.sources()) == {"s1", "s2"}


def test_persist_goes_through_memory_store():
    class FakeMem:
        def __init__(self):
            self.saved = []

        def remember_evidence(self, mission_id, evidence):
            self.saved.append((mission_id, evidence))

    graph = EvidenceGraph()
    graph.assert_claim("A", "x", "1", confidence=0.8)
    memory = FakeMem()
    graph.persist(memory, "m1")
    assert memory.saved and memory.saved[0][0] == "m1"
