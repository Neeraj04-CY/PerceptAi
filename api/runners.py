"""Runner service layer — the control-plane side of distributed execution.

A runner is a machine that executes work through the ONE runtime. The plane
never runs logic here; it registers runners, hands out SIGNED work, and tracks
liveness. Routes import from this module; it never imports routes.

Pure helpers (token minting, status derivation, work-order construction) are
separated from DB calls so the protocol is unit-testable without Supabase.
The runner app (runner/) reuses the pure helpers to verify what it receives.
"""
from __future__ import annotations

import hashlib
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from config import config
from runner_signing import (
    ED25519,
    HMAC_SHA256,
    derive_runner_key,
    private_key_from_seed,
    public_key_for,
    sign_work_order,
    sign_work_order_ed25519,
    verify_request,
)

RUNNER_HINT = ("runner tables unavailable — apply "
               "api/migrations/003_runners.sql to this database")

# A runner is considered offline if it has not heartbeat within this window.
OFFLINE_AFTER_S = 45


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ------------------------------------------------------------ pure helpers

def new_runner_token() -> tuple[str, str, str]:
    """(token, token_hash, prefix). The plaintext token is returned to the
    caller ONCE; only its SHA-256 hash is stored — same model as api_keys."""
    token = f"rk_{_secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash, token[:12]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def derive_status(last_heartbeat_at: Optional[str], current_session_id: Optional[str],
                  now: Optional[datetime] = None,
                  readiness: Optional[dict] = None) -> str:
    """offline | online | busy | <readiness state> — derived, never a stored
    source of truth that can drift.

    Two facts, two owners, one displayed state: liveness and the claim are the
    plane's facts (heartbeat, current_session_id); whether the desktop can be
    driven is the HOST's fact, reported on the heartbeat. A live runner whose
    workstation is locked is neither 'online' (it cannot take work) nor
    'offline' (it is right there, healthy, waiting) — it is 'locked', and
    saying so is the whole point of session truth.
    """
    now = now or utc_now()
    if not last_heartbeat_at:
        return "offline"
    try:
        hb = datetime.fromisoformat(str(last_heartbeat_at))
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "offline"
    if (now - hb).total_seconds() > OFFLINE_AFTER_S:
        return "offline"
    if current_session_id:
        return "busy"  # a claim outranks readiness: it IS executing
    if readiness and not readiness.get("can_execute", True):
        return str(readiness.get("state") or "unknown")
    return "online"


def is_available(status: str) -> bool:
    """Can this runner take work right now? The ONE definition — used by
    dispatch's fleet checks so 'no runner is online' means what it says."""
    return status in ("online", "busy")


def build_work_order(session: dict[str, Any], *, approval_risk_threshold: str = "",
                     available_secrets: Optional[list[str]] = None,
                     egress_policy: Optional[dict] = None,
                     issued_at: Optional[datetime] = None,
                     ttl_seconds: int = 300) -> dict[str, Any]:
    """The signed payload a runner executes. Transport-agnostic and minimal:
    the plain-English instruction, the workspace risk policy the engine gates
    on, identifiers to stream results back, and issuance/expiry + nonce so a
    stale or replayed order is rejected.

    Secret NAMES (never values) are included so the runner's planner can
    reference them; the runner fetches each value on demand over an authorized
    channel and never persists it. The signature covers the names, so the set
    of usable secrets can't be tampered in transit."""
    issued_at = issued_at or utc_now()
    return {
        "session_id": str(session["id"]),
        "instruction": session["instruction"],
        "mode": "task",
        "org_id": str(session["org_id"]) if session.get("org_id") else None,
        "workspace_id": str(session["workspace_id"]) if session.get("workspace_id") else None,
        "approval_risk_threshold": approval_risk_threshold or "",
        "available_secrets": sorted(available_secrets or []),
        # Signed, so a runner cannot be tricked into a laxer egress policy than
        # its workspace declared: tampering invalidates the whole order.
        "egress_policy": egress_policy or {},
        "issued_at": _iso(issued_at),
        "expires_at": _iso(issued_at + timedelta(seconds=ttl_seconds)),
        "nonce": _secrets.token_hex(8),
    }


def plane_private_key() -> str:
    """The plane's Ed25519 identity, derived from the secret it already holds.
    A dedicated KMS-held key is the documented next step and swaps in here."""
    return private_key_from_seed(config.RUNNER_SIGNING_KEY)


def plane_public_key() -> str:
    """Safe to publish: runners verify work orders with it."""
    return public_key_for(plane_private_key())


def sign_for_runner(runner_id: str, work_order: dict[str, Any],
                    key_algorithm: str = HMAC_SHA256) -> dict[str, Any]:
    """Wrap a work order with its signature for delivery.

    An enrolled runner gets an Ed25519 signature from the PLANE's private key —
    it can verify authenticity without holding any secret capable of forging
    work. A legacy runner keeps the symmetric per-runner HMAC until it enrolls.
    """
    if key_algorithm == ED25519:
        signature = sign_work_order_ed25519(plane_private_key(), work_order)
    else:
        key = derive_runner_key(config.RUNNER_SIGNING_KEY, str(runner_id))
        signature = sign_work_order(key, work_order)
    return {"work_order": work_order, "signature": signature,
            "algorithm": key_algorithm}


def public_runner(row: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """A runner row shaped for the API — never leaks the token hash (nor the
    runner's public key material), and reports the derived (not stored) status
    plus the host's self-explaining readiness."""
    readiness = row.get("readiness") or {}
    return {
        "id": row["id"],
        "name": row.get("name", ""),
        "token_prefix": row.get("token_prefix", ""),
        "workspace_id": row.get("workspace_id"),
        "capabilities": row.get("capabilities") or {},
        "current_session_id": row.get("current_session_id"),
        "last_heartbeat_at": row.get("last_heartbeat_at"),
        "status": derive_status(row.get("last_heartbeat_at"),
                                row.get("current_session_id"), now, readiness),
        "readiness": readiness,
        "created_at": row.get("created_at"),
    }


# --------------------------------------------------------------- DB layer

def _guard(exc: Exception) -> None:
    """Turn a missing-table error into an honest 503 with the fix, matching
    the platform migration guard. Re-raise anything else."""
    if "runners" in str(exc).lower() and "exist" in str(exc).lower():
        raise HTTPException(503, RUNNER_HINT)
    raise exc


def register_runner(db, *, user_id: str, org_id: str, name: str,
                    workspace_id: Optional[str] = None,
                    capabilities: Optional[dict] = None) -> dict[str, Any]:
    """Create a runner and return its one-time secrets (token + signing key)
    plus the public row. The token is never recoverable after this call."""
    token, token_hash, prefix = new_runner_token()
    row = {
        "org_id": org_id,
        "workspace_id": workspace_id,
        "name": name or "runner",
        "token_hash": token_hash,
        "token_prefix": prefix,
        "capabilities": capabilities or {},
        "created_by": user_id,
    }
    try:
        created = db.table("runners").insert(row).execute().data[0]
    except Exception as e:
        _guard(e)
    signing_key = derive_runner_key(config.RUNNER_SIGNING_KEY, str(created["id"]))
    return {
        "runner": public_runner(created),
        "token": token,              # shown once — the bootstrap credential
        "signing_key": signing_key,  # shown once; legacy HMAC path (deprecated)
        # The runner verifies work orders with this and needs no secret to do
        # so. It generates its OWN keypair on first start and enrolls the
        # public half; the private half never leaves that machine.
        "plane_public_key": plane_public_key(),
    }


def authenticate_runner(db, token: str) -> dict[str, Any]:
    """Resolve a runner token to its row, or 401. Runner-scoped credential —
    distinct from user JWTs and pk_* API keys."""
    if not token:
        raise HTTPException(401, "Missing runner token")
    try:
        rows = db.table("runners").select("*").eq(
            "token_hash", hash_token(token)).limit(1).execute().data or []
    except Exception as e:
        _guard(e)
    if not rows:
        raise HTTPException(401, "Invalid runner token")
    return rows[0]


def enroll_runner(db, runner: dict[str, Any], public_key: str) -> dict[str, Any]:
    """Trust-on-first-use enrollment of a runner's own public key.

    The bearer token issued at registration is a BOOTSTRAP credential: it is
    good for exactly one thing beyond identifying the row — publishing the
    runner's public key, once. After that the key is the identity, and the
    plane requires a valid signature on every request.

    Re-enrolling an already-enrolled runner is refused. Rotation is therefore an
    explicit, audited operator action (revoke + re-register), not something a
    leaked token can do quietly. That is the honest limit of TOFU, stated rather
    than hidden: a token stolen BEFORE first enrollment can enrol an attacker's
    key, so a runner should be started promptly after registration.
    """
    if not public_key or len(public_key) < 40:
        raise HTTPException(400, "a valid ed25519 public key is required")
    if runner.get("public_key"):
        raise HTTPException(
            409, "this runner has already enrolled a key; re-register the runner "
                 "to rotate its identity")
    now = utc_now()
    try:
        db.table("runners").update({
            "public_key": public_key,
            "key_algorithm": ED25519,
            "key_registered_at": _iso(now),
            "updated_at": _iso(now),
        }).eq("id", runner["id"]).execute()
    except Exception as e:
        _guard(e)
    return {"enrolled": True, "algorithm": ED25519, "plane_public_key": plane_public_key()}


def verify_runner_request(runner: dict[str, Any], *, method: str, path: str,
                          body: bytes, timestamp: str, nonce: str,
                          signature: str) -> None:
    """Authenticate a request as coming from THIS runner's private key.

    Enforced for every enrolled runner. A legacy (un-enrolled) runner is still
    accepted on its bearer token alone, so upgrading the fleet never causes an
    outage — but once a runner has a key, a token alone is no longer enough to
    impersonate it.
    """
    if runner.get("key_algorithm") != ED25519 or not runner.get("public_key"):
        return  # legacy runner: bearer token only (migration path)
    if not (signature and timestamp):
        raise HTTPException(401, "this runner is enrolled and must sign its requests")
    ok, reason = verify_request(runner["public_key"], method, path, body,
                                timestamp, nonce or "", signature)
    if not ok:
        raise HTTPException(401, f"runner request rejected: {reason}")


def record_heartbeat(db, runner_id: str, *, current_session_id: Optional[str] = None,
                     readiness: Optional[dict] = None) -> None:
    """Liveness ping + session truth. Also renews the lease on any session the
    runner is currently executing, so a live runner never loses its claim."""
    now = utc_now()
    patch: dict[str, Any] = {
        "last_heartbeat_at": _iso(now),
        "current_session_id": current_session_id,
        "status": derive_status(_iso(now), current_session_id, now, readiness),
        "updated_at": _iso(now),
    }
    if readiness is not None:
        patch["readiness"] = readiness
    try:
        db.table("runners").update(patch).eq("id", runner_id).execute()
        if current_session_id:
            db.table("sessions").update({
                "claim_expires_at": _iso(now + timedelta(seconds=config.RUNNER_LEASE_SECONDS)),
            }).eq("id", current_session_id).eq("runner_id", runner_id).execute()
    except Exception as e:
        _guard(e)


def reclaim_decision(status: str, attempts: int, max_attempts: int) -> Optional[dict[str, Any]]:
    """The safe recovery for a stale (expired-lease) session — ONE tested source
    of truth. A run that never started is requeued; one that was mid-execution
    is dead-lettered, because a real-screen task is not idempotent and must
    never be silently re-run. Returns the fields to set, or None to leave it."""
    if status == "claimed":
        # Never started executing (no events yet) — safe to hand to another runner.
        if attempts >= max_attempts:
            return {"status": "failed", "runner_id": None, "claim_expires_at": None,
                    "error": "no runner could start this work after repeated attempts",
                    "completed_at": _iso(utc_now())}
        return {"status": "queued", "runner_id": None, "claim_expires_at": None}
    if status == "running":
        # Execution had begun — fail honestly rather than risk duplicate actions.
        return {"status": "failed", "runner_id": None, "claim_expires_at": None,
                "error": "runner disconnected mid-execution; not auto-retried to avoid duplicate actions",
                "completed_at": _iso(utc_now())}
    return None


def reclaim_stale(db, max_attempts: Optional[int] = None) -> int:
    """Requeue/dead-letter sessions whose lease expired (a runner went away).
    Lazy cleanup — called before a claim, so no background loop is needed.
    Returns how many were reclaimed. Never raises into the claim path."""
    max_attempts = config.RUNNER_MAX_ATTEMPTS if max_attempts is None else max_attempts
    try:
        rows = db.table("sessions").select(
            "id, status, attempts, claim_expires_at, org_id, workspace_id, "
            "workflow_id, instruction").in_(
            "status", ["claimed", "running"]).lt(
            "claim_expires_at", _iso(utc_now())).limit(100).execute().data or []
    except Exception:
        # Pre-004 schema (no workflow_id): reclaim must keep working — retry
        # with the 003 column set; attention is skipped without org context.
        try:
            rows = db.table("sessions").select(
                "id, status, attempts, claim_expires_at").in_(
                "status", ["claimed", "running"]).lt(
                "claim_expires_at", _iso(utc_now())).limit(100).execute().data or []
        except Exception:
            return 0
    reclaimed = 0
    for row in rows:
        update = reclaim_decision(row.get("status", ""), int(row.get("attempts", 0) or 0), max_attempts)
        if not update:
            continue
        try:
            db.table("sessions").update(update).eq("id", row["id"]).execute()
            reclaimed += 1
        except Exception:
            continue
        # A dead-letter is uncertain-progress work — it is NEVER policy-retried
        # (that stays the reclaim invariant); it goes to a human instead.
        if update.get("status") == "failed" and row.get("org_id"):
            try:
                from attention import raise_attention
                raise_attention(
                    db, row["org_id"], kind="dead_letter", ref=str(row["id"]),
                    title="A dispatched run was dead-lettered",
                    detail={"error": update.get("error"),
                            "instruction": str(row.get("instruction", ""))[:200]},
                    workspace_id=row.get("workspace_id"),
                    workflow_id=row.get("workflow_id"),
                    session_id=str(row["id"]))
            except Exception:
                pass
    return reclaimed


def claim_next(db, runner: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Atomically claim the oldest queued session for this runner's org (and
    workspace pin, if any). Returns the claimed session row, or None when the
    queue is empty. Race-safe via the SKIP LOCKED claim function."""
    try:
        rows = db.rpc("claim_next_session", {
            "p_runner_id": runner["id"],
            "p_org_id": runner["org_id"],
            "p_workspace_id": runner.get("workspace_id"),
            "p_lease_seconds": config.RUNNER_LEASE_SECONDS,
        }).execute().data or []
    except Exception as e:
        _guard(e)
    return rows[0] if rows else None


def workspace_approval_threshold(db, workspace_id: Optional[str]) -> str:
    """The workspace risk-approval threshold (policy as data), '' if none.
    Never fails execution over a policy lookup."""
    if not workspace_id:
        return ""
    try:
        rows = db.table("workspaces").select("policy").eq(
            "id", workspace_id).limit(1).execute().data or []
        policy = (rows[0].get("policy") if rows else None) or {}
        return str(policy.get("approval_risk_threshold", "") or "")
    except Exception:
        return ""


def workspace_egress_policy(db, workspace_id: Optional[str]) -> dict:
    """The workspace data-egress policy (policy as data), {} if none.

    A lookup failure returns {} — the documented default (allow). Failing
    CLOSED here would brick every run in the org on a transient DB blip; the
    honest control for "nothing may leave" is an explicit `deny` policy, which
    is stored and therefore readable. A missing row means the customer never
    expressed a restriction, not that they expressed the strictest one.
    """
    if not workspace_id:
        return {}
    try:
        rows = db.table("workspaces").select("egress_policy").eq(
            "id", workspace_id).limit(1).execute().data or []
        return (rows[0].get("egress_policy") if rows else None) or {}
    except Exception:
        return {}


def issue_work_order(db, runner: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Build + sign the work order for a freshly claimed session, using whichever
    identity generation this runner has enrolled."""
    threshold = workspace_approval_threshold(db, session.get("workspace_id"))
    order = build_work_order(session, approval_risk_threshold=threshold,
                             available_secrets=_secret_names(db, session),
                             egress_policy=workspace_egress_policy(
                                 db, session.get("workspace_id")))
    return sign_for_runner(runner["id"], order,
                           key_algorithm=str(runner.get("key_algorithm") or HMAC_SHA256))


def _secret_names(db, session: dict[str, Any]) -> list[str]:
    """Secret NAMES in the session's scope (never values) — for the work order."""
    try:
        from secrets_resolver import build_local_resolver
        resolver = build_local_resolver(db, session.get("org_id"), session.get("workspace_id"))
        return resolver.names() if resolver is not None else []
    except Exception:
        return []


def enqueue_session(db, *, user_id: str, org_id: str, instruction: str,
                    workspace_id: Optional[str] = None,
                    workflow_id: Optional[str] = None,
                    api_key_id: Optional[str] = None,
                    origin: str = "user",
                    retry_of: Optional[str] = None,
                    retry_count: int = 0,
                    target_runner_id: Optional[str] = None) -> dict[str, Any]:
    """Create a session in the work queue (status='queued') for a runner to
    claim. This is the plane's dispatch primitive; the runner never creates
    its own work. A target_runner_id pins the work to one runner (only it can
    claim); origin/retry_of/retry_count carry unattended-dispatch lineage."""
    row = {
        "user_id": user_id,
        "org_id": org_id,
        "workspace_id": workspace_id,
        "workflow_id": workflow_id,
        "api_key_id": api_key_id,
        "instruction": instruction,
        "status": "queued",
        "origin": origin if origin != "user" else None,  # column default is 'user'
        "retry_of": retry_of,
        "retry_count": retry_count or None,
        "target_runner_id": target_runner_id,
    }
    row = {k: v for k, v in row.items() if v is not None}
    try:
        return db.table("sessions").insert(row).execute().data[0]
    except Exception as e:
        _guard(e)


def list_runners(db, org_id: str) -> list[dict[str, Any]]:
    try:
        rows = db.table("runners").select("*").eq(
            "org_id", org_id).order("created_at", desc=True).execute().data or []
    except Exception as e:
        _guard(e)
    now = utc_now()
    return [public_runner(r, now) for r in rows]
