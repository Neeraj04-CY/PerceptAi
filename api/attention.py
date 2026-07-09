"""The Attention surface — "what needs a human right now", without watching.

Unattended runs reach an operator ONLY through here: terminal failures,
dead-lettered work, pending approvals, blocked schedules, empty fleets. Items
are derived from facts the plane already persists; nothing here is a second
source of truth. One OPEN item per (org, kind, ref) — a repeating condition
updates nothing and never floods the inbox; acking closes it.

Notification is additive and provider-agnostic: one HMAC-signed webhook per
workspace (the customer routes it to Slack/Teams/pager/email themselves).
Delivery is best-effort with backoff on a background thread — it never blocks
dispatch, execution, or a request handler, and a missing webhook is fine.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

WEBHOOK_TIMEOUT_S = 5
WEBHOOK_ATTEMPTS = 3
WEBHOOK_BACKOFF_S = 2.0  # 2s, 4s between attempts

KINDS = ("run_failed", "dead_letter", "approval_pending", "no_runner", "schedule_blocked")


# ------------------------------------------------------------ pure helpers

def sign_webhook(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the exact request body — receivers verify with the
    secret shown once when the webhook was configured."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def webhook_payload(item: dict[str, Any]) -> dict[str, Any]:
    """The wire shape receivers integrate against. Names only, never values;
    the payload carries the same facts as the inbox item and nothing more."""
    return {
        "type": "perceptai.attention",
        "kind": item.get("kind", ""),
        "title": item.get("title", ""),
        "detail": item.get("detail") or {},
        "org_id": str(item["org_id"]) if item.get("org_id") else None,
        "workspace_id": str(item["workspace_id"]) if item.get("workspace_id") else None,
        "session_id": str(item["session_id"]) if item.get("session_id") else None,
        "workflow_id": str(item["workflow_id"]) if item.get("workflow_id") else None,
        "created_at": item.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------- inbox

def raise_attention(db, org_id: str, *, kind: str, ref: str, title: str,
                    detail: Optional[dict] = None,
                    workspace_id: Optional[str] = None,
                    workflow_id: Optional[str] = None,
                    session_id: Optional[str] = None,
                    notify: bool = True) -> Optional[dict[str, Any]]:
    """Create an attention item (deduped on open (org, kind, ref)) and fire
    the workspace webhook. Never raises — observability must not break the
    path that produced the fact."""
    try:
        existing = db.table("attention_items").select("id").eq("org_id", org_id).eq(
            "kind", kind).eq("ref", str(ref)).eq("status", "open").limit(1).execute().data or []
        if existing:
            return None
        row = {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "kind": kind,
            "ref": str(ref),
            "title": title,
            "detail": detail or {},
            "session_id": session_id,
            "workflow_id": workflow_id,
            "status": "open",
        }
        created = db.table("attention_items").insert(
            {k: v for k, v in row.items() if v is not None}).execute().data[0]
    except Exception:
        return None  # racing duplicate hits the unique index; anything else is non-fatal
    if notify and workspace_id:
        notify_workspace(db, workspace_id, webhook_payload(created))
    return created


def ack_attention(db, org_id: str, item_id: str, user_id: Optional[str]) -> bool:
    updated = db.table("attention_items").update({
        "status": "acked",
        "acked_by": user_id or None,
        "acked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", item_id).eq("org_id", org_id).eq("status", "open").execute().data
    return bool(updated)


def list_attention(db, org_id: str, *, status: str = "open",
                   limit: int = 50) -> list[dict[str, Any]]:
    return db.table("attention_items").select("*").eq("org_id", org_id).eq(
        "status", status).order("created_at", desc=True).limit(limit).execute().data or []


# ----------------------------------------------------------------- webhook

def notify_workspace(db, workspace_id: str, payload: dict[str, Any]) -> None:
    """Deliver the payload to the workspace's webhook, if configured. Reads
    the config here (cheap, always current) and hands delivery to a daemon
    thread so callers never wait on the network."""
    try:
        rows = db.table("workspaces").select(
            "notify_webhook_url, notify_webhook_secret").eq(
            "id", workspace_id).limit(1).execute().data or []
        url = (rows[0].get("notify_webhook_url") if rows else None) or ""
        secret = (rows[0].get("notify_webhook_secret") if rows else None) or ""
    except Exception:
        return
    if not url:
        return
    threading.Thread(target=_deliver, args=(url, secret, payload), daemon=True).start()


def _deliver(url: str, secret: str, payload: dict[str, Any]) -> None:
    """Bounded best-effort delivery. The signature covers the exact bytes sent."""
    import httpx

    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-PerceptAI-Signature"] = sign_webhook(secret, body)
    for attempt in range(WEBHOOK_ATTEMPTS):
        try:
            response = httpx.post(url, content=body, headers=headers,
                                  timeout=WEBHOOK_TIMEOUT_S)
            if response.status_code < 500:
                return  # delivered, or a 4xx that retrying won't fix
        except Exception:
            pass
        if attempt < WEBHOOK_ATTEMPTS - 1:
            time.sleep(WEBHOOK_BACKOFF_S * (attempt + 1))
