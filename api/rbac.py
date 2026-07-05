"""Role-based access control as data.

Four roles, one permission matrix, zero framework coupling — this module
is pure so it is unit-testable and reusable by any transport. Routes
translate a False into HTTP 403.
"""
from __future__ import annotations

# Rank order matters: a role holds every permission of the roles below it.
ROLES = ("owner", "admin", "member", "viewer")
_RANK = {role: i for i, role in enumerate(ROLES)}  # owner=0 ... viewer=3

# permission -> least-privileged role that holds it.
PERMISSIONS: dict[str, str] = {
    "org.manage": "owner",         # rename, plan, delete
    "members.manage": "admin",     # invite, remove, change roles
    "workspaces.manage": "admin",  # create, edit, archive workspaces
    "secrets.manage": "admin",     # create, delete secrets
    "policy.manage": "admin",      # approval/allowlist/budget policy
    "approvals.decide": "admin",   # approve or deny pending work
    "keys.manage": "member",       # own API keys
    "workflows.edit": "member",    # author and publish workflows
    "execute": "member",           # run tasks and missions
    "audit.read": "member",        # read audit and event history
    "view": "viewer",              # dashboards, sessions, reports
}


def is_role(value: str) -> bool:
    return value in _RANK


def can(role: str, permission: str) -> bool:
    """True when `role` holds `permission`. Unknown roles or permissions
    are denied — RBAC fails closed."""
    required = PERMISSIONS.get(permission)
    if required is None or role not in _RANK:
        return False
    return _RANK[role] <= _RANK[required]


def assignable_roles(actor_role: str) -> list[str]:
    """Roles an actor may grant: never above their own."""
    if actor_role not in _RANK:
        return []
    return [role for role in ROLES if _RANK[role] >= _RANK[actor_role]]
