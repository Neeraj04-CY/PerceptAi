"""Sprint 8 Step 4 — the Attention surface: deduped inbox items, ack, and the
HMAC-signed provider-agnostic webhook. No network — delivery is verified at
the signing/payload boundary; the HTTP retry loop is deliberately dumb.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))
sys.path.append(str(Path(__file__).parent))

from supafake import FakeSupabase  # noqa: E402
import attention as att  # noqa: E402


def _raise(db, **over):
    kw = dict(kind="run_failed", ref="sess-1", title="Scheduled run failed",
              detail={"error": "boom"}, workspace_id="ws-1",
              workflow_id="wf-1", session_id="sess-1")
    kw.update(over)
    return att.raise_attention(db, "org-1", **kw)


# ----------------------------------------------------------------- inbox

def test_raise_attention_creates_open_item():
    db = FakeSupabase()
    item = _raise(db)
    assert item["status"] == "open" and item["kind"] == "run_failed"
    assert att.list_attention(db, "org-1") == [item]


def test_open_items_dedup_per_org_kind_ref():
    db = FakeSupabase()
    first = _raise(db)
    assert _raise(db) is None                        # same condition, no flood
    assert len(db.rows["attention_items"]) == 1
    # a DIFFERENT kind on the same ref is a different fact
    assert _raise(db, kind="dead_letter") is not None
    # acking reopens the door: the condition recurring is news again
    assert att.ack_attention(db, "org-1", first["id"], "user-1") is True
    assert _raise(db) is not None


def test_ack_is_idempotent_and_org_scoped():
    db = FakeSupabase()
    item = _raise(db)
    assert att.ack_attention(db, "other-org", item["id"], "user-1") is False
    assert att.ack_attention(db, "org-1", item["id"], "user-1") is True
    assert att.ack_attention(db, "org-1", item["id"], "user-1") is False  # already closed
    assert att.list_attention(db, "org-1") == []
    assert att.list_attention(db, "org-1", status="acked")[0]["acked_by"] == "user-1"


def test_raise_attention_never_raises_on_broken_db():
    class Boom:
        def table(self, _):
            raise RuntimeError("db down")
    assert att.raise_attention(Boom(), "org-1", kind="run_failed", ref="x",
                               title="t") is None   # observability never breaks the path


# ----------------------------------------------------------------- webhook

def test_sign_webhook_is_verifiable_hmac_sha256():
    body = b'{"type":"perceptai.attention"}'
    sig = att.sign_webhook("whsec_123", body)
    expected = hmac.new(b"whsec_123", body, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"
    assert att.sign_webhook("other", body) != sig    # per-secret


def test_webhook_payload_carries_facts_only():
    payload = att.webhook_payload({
        "kind": "run_failed", "title": "t", "detail": {"error": "boom"},
        "org_id": "org-1", "workspace_id": "ws-1", "session_id": "sess-1",
        "workflow_id": "wf-1", "created_at": "2026-07-09T09:00:00+00:00"})
    assert payload["type"] == "perceptai.attention"
    assert payload["session_id"] == "sess-1"
    body = json.dumps(payload)                        # JSON-serializable as sent
    assert "secret" not in body.lower()               # names/facts only, never values


def test_configured_webhook_fires_on_new_item(monkeypatch):
    db = FakeSupabase()
    db.rows["workspaces"].append({
        "id": "ws-1", "notify_webhook_url": "https://hooks.example/x",
        "notify_webhook_secret": "whsec_1"})
    sent = []
    monkeypatch.setattr(att, "notify_workspace",
                        lambda _db, ws, payload: sent.append((ws, payload)))
    _raise(db)
    assert sent and sent[0][0] == "ws-1"
    assert sent[0][1]["kind"] == "run_failed"
    _raise(db)                                        # deduped -> no second delivery
    assert len(sent) == 1


def test_unconfigured_workspace_is_silently_fine(monkeypatch):
    db = FakeSupabase()                               # no workspace row at all
    spawned = []
    monkeypatch.setattr(att.threading, "Thread",
                        lambda **kw: spawned.append(kw))
    att.notify_workspace(db, "ws-1", {"type": "perceptai.attention"})
    assert spawned == []                              # nothing to deliver, no thread
