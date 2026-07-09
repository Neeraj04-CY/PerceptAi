"""Organization platform: orgs, members (RBAC), workspaces, secrets,
audit and usage. Every mutation lands in the control-plane audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from config import config
from database import get_service_db
from models import (
    MemberAddRequest,
    MemberUpdateRequest,
    OrgCreateRequest,
    SecretCreateRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
    WorkspaceWebhookRequest,
)
from orgs import (
    ensure_personal_org,
    get_membership,
    get_workspace,
    list_orgs,
    record_audit,
    require_permission,
    slugify,
    utc_now,
)
from plans import get_plan
from rbac import ROLES, assignable_roles, can, is_role
from secrets_crypto import derive_key, encrypt

router = APIRouter(prefix="/orgs", tags=["organizations"])


def _actor(user: dict) -> tuple[str, str]:
    return user["sub"], user.get("email", "")


# ------------------------------------------------------------------ orgs

@router.get("")
async def my_orgs(current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    orgs = list_orgs(db, user_id)
    if not orgs:
        orgs = [ensure_personal_org(db, user_id, email)]
    return orgs


@router.post("")
async def create_org(body: OrgCreateRequest,
                     current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Organization name is required")
    org = {
        "id": str(uuid.uuid4()),
        "name": name,
        "slug": f"{slugify(name)}-{uuid.uuid4().hex[:6]}",
        "plan_id": "free",
        "is_personal": False,
        "created_by": user_id,
    }
    db.table("organizations").insert(org).execute()
    db.table("organization_members").insert({
        "org_id": org["id"], "user_id": user_id, "role": "owner",
    }).execute()
    db.table("workspaces").insert({
        "org_id": org["id"], "name": "Default", "slug": "default",
        "description": "Default workspace", "created_by": user_id,
    }).execute()
    record_audit(db, org["id"], user_id, email, "org.created", name)
    return {**org, "role": "owner"}


@router.get("/{org_id}")
async def org_detail(org_id: str,
                     current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, _ = _actor(current_user)
    role = require_permission(db, org_id, user_id, "view")
    rows = db.table("organizations").select("*").eq("id", org_id).execute().data
    if not rows:
        raise HTTPException(404, "Organization not found")
    org = rows[0]
    members = db.table("organization_members").select("user_id").eq(
        "org_id", org_id).execute().data or []
    workspaces = db.table("workspaces").select("*").eq(
        "org_id", org_id).order("created_at").execute().data or []
    for ws in workspaces:  # the webhook signing secret is write-only, like vault values
        ws.pop("notify_webhook_secret", None)
    return {
        **org,
        "role": role,
        "plan": get_plan(org.get("plan_id"), db),
        "member_count": len(members),
        "workspaces": workspaces,
    }


# --------------------------------------------------------------- members

@router.get("/{org_id}/members")
async def members(org_id: str,
                  current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    require_permission(db, org_id, current_user["sub"], "view")
    rows = db.table("organization_members").select("*").eq(
        "org_id", org_id).execute().data or []
    users = {}
    if rows:
        ids = [r["user_id"] for r in rows]
        for u in db.table("users").select("id, email").in_("id", ids).execute().data or []:
            users[u["id"]] = u["email"]
    return [
        {"user_id": r["user_id"], "email": users.get(r["user_id"], ""),
         "role": r["role"], "joined_at": r.get("created_at")}
        for r in rows
    ]


@router.post("/{org_id}/members")
async def add_member(org_id: str, body: MemberAddRequest,
                     current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    actor_role = require_permission(db, org_id, user_id, "members.manage")
    if body.role not in assignable_roles(actor_role):
        raise HTTPException(403, f"Role '{actor_role}' cannot grant '{body.role}'")
    target = db.table("users").select("id, email").eq(
        "email", body.email).execute().data
    if not target:
        raise HTTPException(404, "No PerceptAI account with that email — "
                                 "they need to sign up first")
    target_id = target[0]["id"]
    if get_membership(db, org_id, target_id) is not None:
        raise HTTPException(409, "Already a member of this organization")
    db.table("organization_members").insert({
        "org_id": org_id, "user_id": target_id, "role": body.role,
    }).execute()
    record_audit(db, org_id, user_id, email, "member.added",
                 body.email, {"role": body.role})
    return {"user_id": target_id, "email": body.email, "role": body.role}


@router.patch("/{org_id}/members/{member_id}")
async def update_member(org_id: str, member_id: str, body: MemberUpdateRequest,
                        current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    actor_role = require_permission(db, org_id, user_id, "members.manage")
    if not is_role(body.role):
        raise HTTPException(400, f"Unknown role '{body.role}' (one of {', '.join(ROLES)})")
    if body.role not in assignable_roles(actor_role):
        raise HTTPException(403, f"Role '{actor_role}' cannot grant '{body.role}'")
    current = get_membership(db, org_id, member_id)
    if current is None:
        raise HTTPException(404, "Member not found")
    if current == "owner" and actor_role != "owner":
        raise HTTPException(403, "Only an owner can change an owner's role")
    db.table("organization_members").update({"role": body.role}).eq(
        "org_id", org_id).eq("user_id", member_id).execute()
    record_audit(db, org_id, user_id, email, "member.role_changed",
                 member_id, {"from": current, "to": body.role})
    return {"user_id": member_id, "role": body.role}


@router.delete("/{org_id}/members/{member_id}")
async def remove_member(org_id: str, member_id: str,
                        current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    actor_role = require_permission(db, org_id, user_id, "members.manage")
    current = get_membership(db, org_id, member_id)
    if current is None:
        raise HTTPException(404, "Member not found")
    if current == "owner" and actor_role != "owner":
        raise HTTPException(403, "Only an owner can remove an owner")
    db.table("organization_members").delete().eq(
        "org_id", org_id).eq("user_id", member_id).execute()
    record_audit(db, org_id, user_id, email, "member.removed", member_id,
                 {"role": current})
    return {"removed": member_id}


# ------------------------------------------------------------ workspaces

@router.post("/{org_id}/workspaces")
async def create_workspace(org_id: str, body: WorkspaceCreateRequest,
                           current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    require_permission(db, org_id, user_id, "workspaces.manage")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Workspace name is required")
    row = {
        "org_id": org_id,
        "name": name,
        "slug": f"{slugify(name)}-{uuid.uuid4().hex[:4]}",
        "description": body.description,
        "environment": body.environment,
        "created_by": user_id,
    }
    created = db.table("workspaces").insert(row).execute().data[0]
    record_audit(db, org_id, user_id, email, "workspace.created", name,
                 workspace_id=created["id"])
    return created


@router.patch("/{org_id}/workspaces/{workspace_id}")
async def update_workspace(org_id: str, workspace_id: str,
                           body: WorkspaceUpdateRequest,
                           current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    # Policy edits (approvals/allowlists/budgets) are a distinct permission.
    permission = "policy.manage" if body.policy is not None else "workspaces.manage"
    require_permission(db, org_id, user_id, permission)
    get_workspace(db, workspace_id, org_id)
    patch = {k: v for k, v in {
        "name": body.name, "description": body.description,
        "environment": body.environment, "policy": body.policy,
        "updated_at": utc_now(),
    }.items() if v is not None}
    updated = db.table("workspaces").update(patch).eq(
        "id", workspace_id).execute().data
    record_audit(db, org_id, user_id, email,
                 "workspace.policy_changed" if body.policy is not None
                 else "workspace.updated",
                 workspace_id, {k: v for k, v in patch.items() if k != "updated_at"},
                 workspace_id=workspace_id)
    return updated[0] if updated else {**patch, "id": workspace_id}


@router.put("/{org_id}/workspaces/{workspace_id}/webhook")
async def set_workspace_webhook(org_id: str, workspace_id: str,
                                body: WorkspaceWebhookRequest,
                                current_user: dict = Depends(get_current_user)):
    """Configure the workspace's Attention webhook. Setting a URL mints a
    fresh HMAC signing secret returned ONCE (write-only afterwards — same
    model as runner tokens); an empty URL clears both."""
    db = get_service_db()
    user_id, email = _actor(current_user)
    require_permission(db, org_id, user_id, "workspaces.manage")
    get_workspace(db, workspace_id, org_id)
    url = (body.url or "").strip()
    if url and not url.startswith("https://"):
        raise HTTPException(400, "Webhook URL must be https://")
    import secrets as _secrets
    secret = f"whsec_{_secrets.token_urlsafe(32)}" if url else None
    db.table("workspaces").update({
        "notify_webhook_url": url or None,
        "notify_webhook_secret": secret,
        "updated_at": utc_now(),
    }).eq("id", workspace_id).execute()
    record_audit(db, org_id, user_id, email,
                 "workspace.webhook_set" if url else "workspace.webhook_cleared",
                 workspace_id, {"url": url or None}, workspace_id=workspace_id)
    return {"url": url or None, "secret": secret}  # secret shown once, never again


# --------------------------------------------------------------- secrets

@router.get("/{org_id}/secrets")
async def list_secrets(org_id: str,
                       current_user: dict = Depends(get_current_user)):
    """Metadata only — secret values are write-only through the API."""
    db = get_service_db()
    require_permission(db, org_id, current_user["sub"], "view")
    rows = db.table("secrets").select(
        "id, name, workspace_id, created_by, created_at, updated_at").eq(
        "org_id", org_id).order("name").execute().data or []
    return rows


@router.post("/{org_id}/secrets")
async def create_secret(org_id: str, body: SecretCreateRequest,
                        current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    require_permission(db, org_id, user_id, "secrets.manage")
    name = body.name.strip().upper().replace(" ", "_")
    if not name or not body.value:
        raise HTTPException(400, "Secret name and value are required")
    if body.workspace_id:
        get_workspace(db, body.workspace_id, org_id)
    ciphertext = encrypt(body.value, derive_key(config.SECRETS_KEY))
    existing = db.table("secrets").select("id").eq("org_id", org_id).eq(
        "name", name).execute().data
    if existing:
        db.table("secrets").update({
            "ciphertext": ciphertext, "updated_at": utc_now(),
        }).eq("id", existing[0]["id"]).execute()
        action = "secret.rotated"
        secret_id = existing[0]["id"]
    else:
        created = db.table("secrets").insert({
            "org_id": org_id, "workspace_id": body.workspace_id,
            "name": name, "ciphertext": ciphertext, "created_by": user_id,
        }).execute().data[0]
        action = "secret.created"
        secret_id = created["id"]
    record_audit(db, org_id, user_id, email, action, name,
                 workspace_id=body.workspace_id)
    return {"id": secret_id, "name": name, "workspace_id": body.workspace_id}


@router.delete("/{org_id}/secrets/{secret_id}")
async def delete_secret(org_id: str, secret_id: str,
                        current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    user_id, email = _actor(current_user)
    require_permission(db, org_id, user_id, "secrets.manage")
    rows = db.table("secrets").select("name").eq("id", secret_id).eq(
        "org_id", org_id).execute().data
    if not rows:
        raise HTTPException(404, "Secret not found")
    db.table("secrets").delete().eq("id", secret_id).execute()
    record_audit(db, org_id, user_id, email, "secret.deleted", rows[0]["name"])
    return {"deleted": secret_id}


# ----------------------------------------------------------------- audit

@router.get("/{org_id}/audit")
async def audit_trail(org_id: str, limit: int = 100,
                      current_user: dict = Depends(get_current_user)):
    db = get_service_db()
    require_permission(db, org_id, current_user["sub"], "audit.read")
    rows = db.table("audit_log").select("*").eq("org_id", org_id).order(
        "created_at", desc=True).limit(min(max(limit, 1), 500)).execute().data or []
    return rows


# ----------------------------------------------------------------- usage

@router.get("/{org_id}/usage")
async def org_usage(org_id: str,
                    current_user: dict = Depends(get_current_user)):
    """Executions this month across the organization's members, against
    the org plan — the budget view Mission Control renders."""
    db = get_service_db()
    require_permission(db, org_id, current_user["sub"], "view")
    org = db.table("organizations").select("plan_id").eq(
        "id", org_id).execute().data
    plan = get_plan(org[0]["plan_id"] if org else None, db)
    member_rows = db.table("organization_members").select("user_id").eq(
        "org_id", org_id).execute().data or []
    month = datetime.now().strftime("%Y-%m")
    used = 0
    if member_rows:
        usage_rows = db.table("usage").select("executions").in_(
            "user_id", [m["user_id"] for m in member_rows]).eq(
            "month", month).execute().data or []
        used = sum(r["executions"] for r in usage_rows)
    limit = plan["monthly_executions"]
    return {
        "month": month,
        "executions_used": used,
        "executions_limit": limit,
        "plan": plan["id"],
        "workforce_limits": plan["limits"],
        "percentage_used": round(used / limit * 100, 1) if limit else 0.0,
    }
