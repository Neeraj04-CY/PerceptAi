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
from runner_signing import derive_runner_key, sign_work_order

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
                  now: Optional[datetime] = None) -> str:
    """offline | online | busy — derived, never a stored source of truth that
    can drift. A runner mid-execution is busy; a fresh heartbeat is online."""
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
    return "busy" if current_session_id else "online"


def build_work_order(session: dict[str, Any], *, approval_risk_threshold: str = "",
                     available_secrets: Optional[list[str]] = None,
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
        "issued_at": _iso(issued_at),
        "expires_at": _iso(issued_at + timedelta(seconds=ttl_seconds)),
        "nonce": _secrets.token_hex(8),
    }


def sign_for_runner(runner_id: str, work_order: dict[str, Any]) -> dict[str, Any]:
    """Wrap a work order with its per-runner signature for delivery."""
    key = derive_runner_key(config.RUNNER_SIGNING_KEY, str(runner_id))
    return {"work_order": work_order, "signature": sign_work_order(key, work_order)}


def public_runner(row: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """A runner row shaped for the API — never leaks the token hash, and
    reports the derived (not stored) status."""
    return {
        "id": row["id"],
        "name": row.get("name", ""),
        "token_prefix": row.get("token_prefix", ""),
        "workspace_id": row.get("workspace_id"),
        "capabilities": row.get("capabilities") or {},
        "current_session_id": row.get("current_session_id"),
        "last_heartbeat_at": row.get("last_heartbeat_at"),
        "status": derive_status(row.get("last_heartbeat_at"),
                                row.get("current_session_id"), now),
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
        "token": token,            # shown once
        "signing_key": signing_key,  # shown once; runner stores it to verify work
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


def record_heartbeat(db, runner_id: str, *, current_session_id: Optional[str] = None) -> None:
    """Liveness ping. Also renews the lease on any session the runner is
    currently executing, so a live runner never loses its claim."""
    now = utc_now()
    try:
        db.table("runners").update({
            "last_heartbeat_at": _iso(now),
            "current_session_id": current_session_id,
            "status": "busy" if current_session_id else "online",
            "updated_at": _iso(now),
        }).eq("id", runner_id).execute()
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
        rows = db.table("sessions").select("id, status, attempts, claim_expires_at").in_(
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


def issue_work_order(db, runner: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    """Build + sign the work order for a freshly claimed session."""
    threshold = workspace_approval_threshold(db, session.get("workspace_id"))
    order = build_work_order(session, approval_risk_threshold=threshold,
                             available_secrets=_secret_names(db, session))
    return sign_for_runner(runner["id"], order)


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
                    api_key_id: Optional[str] = None) -> dict[str, Any]:
    """Create a session in the work queue (status='queued') for a runner to
    claim. This is the plane's dispatch primitive; the runner never creates
    its own work."""
    row = {
        "user_id": user_id,
        "org_id": org_id,
        "workspace_id": workspace_id,
        "workflow_id": workflow_id,
        "api_key_id": api_key_id,
        "instruction": instruction,
        "status": "queued",
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
