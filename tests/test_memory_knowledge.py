"""Knowledge store roundtrip against a real SQLite MemoryStore."""
from perceptai.contracts import Evidence
from perceptai.memory import MemoryStore


def test_evidence_persists_and_recalls(tmp_path):
    store = MemoryStore(tmp_path / "mem.db")
    store.remember_evidence(
        "task-1",
        [
            Evidence(kind="price", label="Acme widget", value="$19.99", source="acme.com", confidence=0.9),
            Evidence(kind="email", label="Acme contact", value="sales@acme.com", source="acme.com", confidence=0.8),
        ],
    )

    rows = store.recall_knowledge(["Acme"])
    assert len(rows) == 2
    assert {r["attribute"] for r in rows} == {"price", "email"}

    rows = store.recall_knowledge(["widget"])
    assert rows and rows[0]["value"] == "$19.99"


def test_recall_matches_values_too(tmp_path):
    store = MemoryStore(tmp_path / "mem.db")
    store.remember_evidence(
        "t", [Evidence(kind="link", label="docs", value="https://docs.acme.com", source="acme.com")]
    )
    assert store.recall_knowledge(["docs.acme"])


def test_recall_ignores_short_terms_and_empty(tmp_path):
    store = MemoryStore(tmp_path / "mem.db")
    assert store.recall_knowledge([]) == []
    assert store.recall_knowledge(["a", "of"]) == []


def test_empty_values_are_not_stored(tmp_path):
    store = MemoryStore(tmp_path / "mem.db")
    store.remember_evidence("t", [Evidence(kind="text", label="x", value="")])
    assert store.recall_knowledge(["x"]) == []


def test_recall_interface_ranks_by_stability(tmp_path):
    store = MemoryStore(tmp_path / "mem.db")
    # "Save" seen three times, "Tools" once — Save is the more stable control.
    for _ in range(3):
        store.remember_interface("editor", [
            {"text": "Save", "type": "button", "x": 100, "y": 50, "confidence": 0.95},
        ])
    store.remember_interface("editor", [
        {"text": "Tools", "type": "menu_item", "x": 200, "y": 50, "confidence": 0.9},
    ])

    recalled = store.recall_interface("editor")
    assert [r["text"] for r in recalled] == ["Save", "Tools"]
    assert recalled[0]["seen_count"] == 3
    assert recalled[0]["type"] == "button"

    assert store.recall_interface("") == []
    assert store.recall_interface("unknown-app") == []
