"""The shared plane<->runner signing protocol.

Lives in the engine package only because that package is the single dependency
BOTH the control plane (api/) and the runner (runner/) already share, so both
import one source of truth without path hacks and the runner wheel gets it for
free. The engine runtime never calls it.

TWO GENERATIONS, ONE MODULE (Chapter IX):

  * Legacy (HMAC-SHA256). A per-runner key derived from a server secret and the
    runner id. Sound, but SYMMETRIC: the plane can mint any runner's key, so
    compromise of the one server secret forges work for the ENTIRE fleet, and a
    stolen runner key is indistinguishable from the runner itself. Retained so
    already-deployed runners keep working through the migration.

  * Ed25519 (asymmetric, mutual). Eliminates shared trust in both directions:
      - The PLANE holds a private key and signs work orders; runners verify with
        the plane's public key. A compromised runner can forge nothing.
      - Each RUNNER generates its own keypair on its own host; the private key
        never leaves it. The plane stores only the public key and verifies every
        request against it. Identity becomes cryptographic rather than a bearer
        secret: stealing a runner's credential compromises exactly one runner,
        and stealing the plane's database compromises no runner's identity.

Blast radius, stated plainly: the plane's private key can still issue work (it
is the issuer — that is unavoidable and is why it belongs in a KMS). Nothing
else is fleet-wide any more.

Request signing binds method, path, timestamp and a hash of the body, so a
captured request cannot be replayed against a different endpoint, mutated, or
replayed later than the freshness window.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional


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


# ===================================================================
# Ed25519 — asymmetric, mutual identity (Chapter IX)
# ===================================================================

ED25519 = "ed25519"
HMAC_SHA256 = "hmac-sha256"

# A signed request is valid only inside this window. Bounds replay of a captured
# request without requiring a distributed nonce cache (which a single-process
# plane cannot honestly provide today). The body hash binds the content, and the
# path binds the endpoint, so a replay can only re-send the identical call.
MAX_CLOCK_SKEW_S = 300


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _ed25519():
    """Lazy import: `cryptography` is already a transitive dependency of both
    the API (Fernet) and the runner, but the engine must import on hosts that
    have neither."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519


def generate_keypair() -> tuple[str, str]:
    """(private_key_b64, public_key_b64). The private half NEVER leaves the host
    that generated it — that is the entire point."""
    ed25519 = _ed25519()
    private = ed25519.Ed25519PrivateKey.generate()
    return private_key_to_b64(private), public_key_b64(private)


def private_key_from_seed(seed_material: str) -> str:
    """Derive a stable Ed25519 private key from an existing server secret.

    Lets an operator adopt asymmetric work-order signing without provisioning a
    new secret: the plane's identity is derived deterministically from the
    secret it already holds. A dedicated key in a KMS is the documented next
    step — this function is why that swap touches only this module.
    """
    ed25519 = _ed25519()
    seed = hashlib.sha256(f"plane-identity:{seed_material}".encode()).digest()
    return private_key_to_b64(ed25519.Ed25519PrivateKey.from_private_bytes(seed))


def private_key_to_b64(private) -> str:
    from cryptography.hazmat.primitives import serialization
    return _b64e(private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()))


def _load_private(private_b64: str):
    return _ed25519().Ed25519PrivateKey.from_private_bytes(_b64d(private_b64))


def _load_public(public_b64: str):
    return _ed25519().Ed25519PublicKey.from_public_bytes(_b64d(public_b64))


def public_key_b64(private) -> str:
    from cryptography.hazmat.primitives import serialization
    return _b64e(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw))


def public_key_for(private_b64: str) -> str:
    """The public half of a private key we hold — safe to publish."""
    return public_key_b64(_load_private(private_b64))


def sign_bytes(private_b64: str, payload: bytes) -> str:
    return _b64e(_load_private(private_b64).sign(payload))


def verify_bytes(public_b64: str, payload: bytes, signature: str) -> bool:
    try:
        _load_public(public_b64).verify(_b64d(signature), payload)
        return True
    except Exception:
        return False  # bad signature, bad key, malformed input — all "no"


# ---------------------------------------------------- work orders (plane -> runner)

def sign_work_order_ed25519(plane_private_b64: str, work_order: dict[str, Any]) -> str:
    return sign_bytes(plane_private_b64, _canonical(work_order))


def verify_work_order_ed25519(plane_public_b64: str, work_order: dict[str, Any],
                              signature: str) -> bool:
    return verify_bytes(plane_public_b64, _canonical(work_order), signature)


# ------------------------------------------------- requests (runner -> plane)

def request_payload(method: str, path: str, body: bytes, timestamp: int,
                    nonce: str) -> bytes:
    """The exact bytes both sides sign. Binds the verb, the endpoint, the body
    and the moment — so a captured signature cannot be moved to another route,
    altered, or replayed outside the freshness window."""
    digest = hashlib.sha256(body or b"").hexdigest()
    return "\n".join([method.upper(), path, str(timestamp), nonce, digest]).encode()


def sign_request(private_b64: str, method: str, path: str, body: bytes,
                 timestamp: int, nonce: str) -> str:
    return sign_bytes(private_b64, request_payload(method, path, body, timestamp, nonce))


def verify_request(public_b64: str, method: str, path: str, body: bytes,
                   timestamp: int, nonce: str, signature: str,
                   now: Optional[int] = None,
                   max_skew_s: int = MAX_CLOCK_SKEW_S) -> tuple[bool, str]:
    """(ok, reason). Freshness is checked BEFORE the signature so an expired
    replay is rejected even if the attacker holds a valid captured signature."""
    now = int(time.time()) if now is None else now
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, "malformed timestamp"
    if abs(now - ts) > max_skew_s:
        return False, "request timestamp outside the freshness window"
    if not verify_bytes(public_b64, request_payload(method, path, body, ts, nonce), signature):
        return False, "signature does not match this runner's registered key"
    return True, ""
