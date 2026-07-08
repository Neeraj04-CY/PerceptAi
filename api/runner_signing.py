"""Signed work orders — the runner executes only work the control plane
issued, unaltered.

Every work order carries an HMAC-SHA256 signature over its canonical JSON.
The key is derived per-runner from a server secret and the runner id, so a
runner can verify only its OWN work: there is no shared global signing key to
leak, and no runner can forge another's orders. The server derives the key on
demand (never stored); the runner receives its key once at registration.

Pure functions, no I/O — trivially testable and reusable by the runner app,
which imports this module to verify what it receives.

Threat model (MVP): protects work-order integrity/authenticity end to end
(defense in depth over TLS, and forward-safe if work is ever relayed through
an intermediary). Asymmetric per-runner keypairs are a documented hardening
fast-follow; they would change only this module, not the protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def derive_runner_key(server_secret: str, runner_id: str) -> str:
    """Per-runner signing key = HMAC(server_secret, runner_id). Deterministic,
    so the server re-derives it on every claim and never stores it; the runner
    is handed this value once at registration and stores it locally."""
    return hmac.new(
        server_secret.encode(), f"runner:{runner_id}".encode(), hashlib.sha256
    ).hexdigest()


def _canonical(payload: dict[str, Any]) -> bytes:
    """Stable serialization so both sides sign the exact same bytes."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_work_order(key: str, work_order: dict[str, Any]) -> str:
    """Signature over the canonical work order (which must NOT already contain
    a 'signature' field)."""
    return hmac.new(key.encode(), _canonical(work_order), hashlib.sha256).hexdigest()


def verify_work_order(key: str, work_order: dict[str, Any], signature: str) -> bool:
    """Constant-time verification. `work_order` is the payload without its
    signature; `signature` is the value that travelled alongside it."""
    expected = sign_work_order(key, work_order)
    return hmac.compare_digest(expected, signature)
