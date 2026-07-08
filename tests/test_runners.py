"""Sprint 4 — control-plane runner protocol (pure logic; no Supabase, no net).

Covers signed work orders and the runner-facing helpers the runner app reuses
to verify what it receives. DB-backed register/heartbeat/claim are exercised
end-to-end by the simulated-runner tests in Step 5."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from config import config  # noqa: E402
import runners as svc  # noqa: E402
from runner_signing import (  # noqa: E402
    derive_runner_key,
    sign_work_order,
    verify_work_order,
)

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ signing

def test_derive_key_is_deterministic_and_per_runner():
    k1 = derive_runner_key("server-secret", "runner-A")
    assert k1 == derive_runner_key("server-secret", "runner-A")   # stable
    assert k1 != derive_runner_key("server-secret", "runner-B")   # per-runner
    assert k1 != derive_runner_key("other-secret", "runner-A")    # per-server


def test_sign_verify_round_trip():
    key = derive_runner_key("s", "r1")
    order = {"session_id": "abc", "instruction": "open notepad", "nonce": "x"}
    sig = sign_work_order(key, order)
    assert verify_work_order(key, order, sig)


def test_verify_rejects_tampered_order():
    key = derive_runner_key("s", "r1")
    order = {"session_id": "abc", "instruction": "open notepad"}
    sig = sign_work_order(key, order)
    tampered = {**order, "instruction": "delete everything"}
    assert not verify_work_order(key, tampered, sig)


def test_verify_rejects_wrong_key_or_signature():
    order = {"session_id": "abc"}
    sig = sign_work_order(derive_runner_key("s", "r1"), order)
    assert not verify_work_order(derive_runner_key("s", "r2"), order, sig)  # other runner
    assert not verify_work_order(derive_runner_key("s", "r1"), order, "deadbeef")


def test_signature_is_order_independent():
    """Canonical serialization → key order in the dict must not matter."""
    key = derive_runner_key("s", "r1")
    a = {"session_id": "abc", "instruction": "x", "nonce": "n"}
    b = {"nonce": "n", "instruction": "x", "session_id": "abc"}
    assert sign_work_order(key, a) == sign_work_order(key, b)


# ------------------------------------------------------------- work orders

def test_build_work_order_shape():
    session = {"id": "sess-1", "instruction": "summarize the news",
               "org_id": "org-1", "workspace_id": "ws-1"}
    order = svc.build_work_order(session, approval_risk_threshold="high",
                                 issued_at=NOW, ttl_seconds=300)
    assert order["session_id"] == "sess-1"
    assert order["instruction"] == "summarize the news"
    assert order["mode"] == "task"
    assert order["approval_risk_threshold"] == "high"
    assert order["workspace_id"] == "ws-1"
    assert order["issued_at"] == NOW.isoformat()
    assert order["expires_at"] == (NOW + timedelta(seconds=300)).isoformat()
    assert order["nonce"]  # replay guard present
    assert "signature" not in order  # signature wraps, never embeds


def test_build_work_order_handles_missing_scope():
    order = svc.build_work_order({"id": "s", "instruction": "x"}, issued_at=NOW)
    assert order["org_id"] is None and order["workspace_id"] is None
    assert order["approval_risk_threshold"] == ""


def test_sign_for_runner_verifiable_by_runner():
    """End to end: the plane signs; the runner verifies with the key it was
    issued at registration (derive_runner_key over the same server secret)."""
    session = {"id": "s9", "instruction": "open files", "org_id": "o", "workspace_id": None}
    order = svc.build_work_order(session, issued_at=NOW)
    signed = svc.sign_for_runner("runner-9", order)

    runner_key = derive_runner_key(config.RUNNER_SIGNING_KEY, "runner-9")
    assert verify_work_order(runner_key, signed["work_order"], signed["signature"])
    # a runner with a different id cannot verify this order
    other_key = derive_runner_key(config.RUNNER_SIGNING_KEY, "runner-8")
    assert not verify_work_order(other_key, signed["work_order"], signed["signature"])


# ------------------------------------------------------------ status + token

def test_derive_status_transitions():
    assert svc.derive_status(None, None, NOW) == "offline"
    stale = (NOW - timedelta(seconds=svc.OFFLINE_AFTER_S + 10)).isoformat()
    assert svc.derive_status(stale, None, NOW) == "offline"
    fresh = (NOW - timedelta(seconds=5)).isoformat()
    assert svc.derive_status(fresh, None, NOW) == "online"
    assert svc.derive_status(fresh, "sess-1", NOW) == "busy"


def test_new_runner_token_shape():
    token, token_hash, prefix = svc.new_runner_token()
    assert token.startswith("rk_")
    assert token_hash == svc.hash_token(token)
    assert prefix == token[:12] and len(prefix) == 12


def test_reclaim_never_started_run_is_requeued():
    d = svc.reclaim_decision("claimed", attempts=1, max_attempts=3)
    assert d["status"] == "queued" and d["runner_id"] is None
    assert "error" not in d  # nothing failed — it just goes back to the queue


def test_reclaim_running_run_is_dead_lettered_not_retried():
    d = svc.reclaim_decision("running", attempts=1, max_attempts=3)
    assert d["status"] == "failed"
    assert "duplicate" in d["error"]  # never silently re-run a mid-flight real-screen task


def test_reclaim_bounds_retries_with_dead_letter():
    # attempts == max -> stop requeueing even a never-started run
    d = svc.reclaim_decision("claimed", attempts=3, max_attempts=3)
    assert d["status"] == "failed" and "repeated attempts" in d["error"]


def test_reclaim_ignores_non_stale_statuses():
    assert svc.reclaim_decision("completed", 1, 3) is None
    assert svc.reclaim_decision("queued", 0, 3) is None


def test_public_runner_never_leaks_token_hash():
    row = {"id": "r1", "name": "desk-01", "token_hash": "SECRET_HASH",
           "token_prefix": "rk_abc", "last_heartbeat_at": (NOW).isoformat(),
           "current_session_id": None, "capabilities": {"os": "windows"}}
    pub = svc.public_runner(row, NOW)
    assert "token_hash" not in pub
    assert pub["token_prefix"] == "rk_abc"
    assert pub["status"] == "online"
