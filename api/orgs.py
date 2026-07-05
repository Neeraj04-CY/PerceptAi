"""Organization service layer.

Membership resolution, personal-org bootstrap, workspace lookups and the
control-plane audit trail. Route modules import from here so they never
import each other. Every user always has an organization: accounts that
predate the platform get a personal org lazily on first touch.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from rbac import can

PLATFORM_HINT = ("platform tables unavailable — apply "
                 "api/migrations/002_platform.sql to this database")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:48] or "org"


def _unique_slug(name: str) -> str:
    return f"{slugify(name)}-{uuid.uuid4().hex[:6]}"


def ensure_personal_org(db, user_id: str, email: str = "") -> dict[str, Any]:
    """The user's primary organization (personal preferred), with their
    role attached. Creates personal org + default workspace on first use."""
    try:
        memberships = db.table("organization_members").select("org_id, role").eq(
            "user_id", user_id).execute().data or []
    except Exception:
        raise HTTPException(503, PLATFORM_HINT)

    if memberships:
        by_org = {m["org_id"]: m["role"] for m in memberships}
        orgs = db.table("organizations").select("*").in_(
            "id", list(by_org)).execute().data or []
        orgs.sort(key=lambda o: (not o.get("is_personal"), o.get("created_at") or ""))
        if orgs:
            org = orgs[0]
            return {**org, "role": by_org[org["id"]]}

    # First touch: bootstrap a personal org around the user's existing plan.
    plan_rows = db.table("user_plans").select("plan_id").eq(
        "user_id", user_id).execute().data or []
    plan_id = plan_rows[0]["plan_id"] if plan_rows else "free"
    display = email.split("@")[0] if email else "Personal"

    org = {
        "id": str(uuid.uuid4()),
        "name": f"{display}'s workspace",
        "slug": _unique_slug(display),
        "plan_id": plan_id,
        "is_personal": True,
        "created_by": user_id,
    }
    db.table("organizations").insert(org).execute()
    db.table("organization_members").insert({
        "org_id": org["id"], "user_id": user_id, "role": "owner",
    }).execute()
    db.table("workspaces").insert({
        "id": str(uuid.uuid4()), "org_id": org["id"],
        "name": "Default", "slug": "default",
        "description": "Default workspace", "created_by": user_id,
    }).execute()
    record_audit(db, org["id"], user_id, email, "org.created", org["name"],
                 {"personal": True})
    return {**org, "role": "owner"}


def list_orgs(db, user_id: str) -> list[dict[str, Any]]:
    try:
        memberships = db.table("organization_members").select("org_id, role").eq(
            "user_id", user_id).execute().data or []
    except Exception:
        raise HTTPException(503, PLATFORM_HINT)
    if not memberships:
        return []
    by_org = {m["org_id"]: m["role"] for m in memberships}
    orgs = db.table("organizations").select("*").in_(
        "id", list(by_org)).execute().data or []
    orgs.sort(key=lambda o: (not o.get("is_personal"), o.get("created_at") or ""))
    return [{**o, "role": by_org[o["id"]]} for o in orgs]


def get_membership(db, org_id: str, user_id: str) -> Optional[str]:
    rows = db.table("organization_members").select("role").eq(
        "org_id", org_id).eq("user_id", user_id).execute().data or []
    return rows[0]["role"] if rows else None


def require_permission(db, org_id: str, user_id: str, permission: str) -> str:
    """The caller's role, or 403/404. RBAC fails closed."""
    try:
        role = get_membership(db, org_id, user_id)
    except Exception:
        raise HTTPException(503, PLATFORM_HINT)
    if role is None:
        raise HTTPException(404, "Organization not found")
    if not can(role, permission):
        raise HTTPException(403, f"Role '{role}' cannot {permission}")
    return role


def get_workspace(db, workspace_id: str, org_id: Optional[str] = None) -> dict:
    query = db.table("workspaces").select("*").eq("id", workspace_id)
    if org_id:
        query = query.eq("org_id", org_id)
    rows = query.execute().data or []
    if not rows:
        raise HTTPException(404, "Workspace not found")
    return rows[0]


def default_workspace(db, org_id: str) -> Optional[dict]:
    rows = db.table("workspaces").select("*").eq("org_id", org_id).order(
        "created_at").limit(1).execute().data or []
    return rows[0] if rows else None


def session_scope(db, user_id: str, workspace_id: Optional[str] = None,
                  workflow_id: Optional[str] = None) -> dict:
    """Optional org/workspace scoping for a session row. Accounts (or
    databases) that predate the platform migration simply get no scope —
    execution must never fail over scoping metadata."""
    scope: dict = {}
    if workflow_id:
        scope["workflow_id"] = workflow_id
    try:
        org = ensure_personal_org(db, user_id)
        scope["org_id"] = org["id"]
        if workspace_id:
            scope["workspace_id"] = workspace_id
    except Exception:
        scope.pop("workflow_id", None)  # column arrives with the same migration
    return scope


def record_audit(db, org_id: str, actor_id: Optional[str], actor_email: str,
                 action: str, target: str = "",
                 detail: Optional[dict] = None,
                 workspace_id: Optional[str] = None) -> None:
    """Control-plane audit. Never raises — an audit failure must not fail
    the action it records (the action itself is already persisted)."""
    try:
        db.table("audit_log").insert({
            "org_id": org_id,
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            "actor_email": actor_email or "",
            "action": action,
            "target": target,
            "detail": detail or {},
        }).execute()
    except Exception:
        pass
