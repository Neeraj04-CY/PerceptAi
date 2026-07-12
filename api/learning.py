"""Learning consent — the legal foundation of the flywheel, present before the
first enterprise contract is signed.

The Verified Evidence Flywheel compounds only if PerceptAI has the RIGHT to
learn from executions. That right is not a feature to add later: if the first
DPA is silent on derivative use, enterprise legal defaults it to "no", and the
flywheel dies in procurement. So the concepts must exist in the product — as
DATA, attributable and auditable — from day one.

This module is the FOUNDATION only. Organizational learning is deliberately NOT
built here: nothing consumes consent yet. What exists is:
  * the consent tiers, as a value exchange (each tier the customer grants earns
    them the corresponding benefit);
  * a per-workspace learning policy (data);
  * an append-only consent ledger — consent is never mutated, only superseded,
    so an auditor can always reconstruct who granted what, when, and under
    which version of the terms;
  * derivative-data and anonymization policy, declared alongside the tier.

Pure helpers are separated from the DB layer so the semantics are unit-tested
without Supabase.
"""
from __future__ import annotations

from typing import Any, Optional

# ------------------------------------------------------------------ tiers
# Each tier is opt-in and additive. A workspace always keeps the benefit of its
# own runs; the higher tiers are a value exchange, never a default.
WORKSPACE_ONLY = "workspace_only"        # your runs improve YOUR workspace. Always on — it is the product.
ANONYMIZED_PRIORS = "anonymized_priors"  # opt-in: contribute de-identified app-level priors; receive everyone's.
MODEL_IMPROVEMENT = "model_improvement"  # opt-in: de-identified traces may train future models.

TIERS = (WORKSPACE_ONLY, ANONYMIZED_PRIORS, MODEL_IMPROVEMENT)

# What each tier grants and what the customer gets back — surfaced in the UI and
# the consent record so the exchange is explicit, never buried.
TIER_TERMS: dict[str, dict[str, str]] = {
    WORKSPACE_ONLY: {
        "grants": "PerceptAI learns your workspace's interfaces and entities to "
                  "improve reliability on your own estate.",
        "benefit": "Every run makes your next run on the same apps more reliable.",
        "shares_outside_workspace": "no",
    },
    ANONYMIZED_PRIORS: {
        "grants": "De-identified, app-level interface priors (never your data, "
                  "never your screens) may be pooled across customers.",
        "benefit": "New workflows start from priors learned across the whole fleet.",
        "shares_outside_workspace": "anonymized_only",
    },
    MODEL_IMPROVEMENT: {
        "grants": "De-identified execution traces may be used to train and "
                  "evaluate future PerceptAI models.",
        "benefit": "Compounding accuracy and lower cost over time.",
        "shares_outside_workspace": "anonymized_only",
    },
}

# The version of the terms a grant is recorded against. Bump when the meaning of
# any tier changes, so historical consent is never silently reinterpreted.
POLICY_VERSION = "2026-07-10.1"

# Anonymization strength a customer can require on any shared tier. Data, not a
# hardcoded behavior — the future learning service will read this.
ANONYMIZATION = ("standard", "strict")


# ------------------------------------------------------------ pure helpers

def default_policy() -> dict[str, Any]:
    """The safe default: learn within the workspace, share NOTHING outside it,
    strongest anonymization if that ever changes. A customer must actively opt
    in to every tier that leaves their boundary."""
    return {
        "tiers": {WORKSPACE_ONLY: True, ANONYMIZED_PRIORS: False,
                  MODEL_IMPROVEMENT: False},
        "anonymization": "strict",
        "derivative_data": "none_outside_workspace",
        "knowledge_owner": "customer",   # who owns the learned knowledge — the customer
        "policy_version": POLICY_VERSION,
    }


def normalize_policy(raw: Optional[dict]) -> dict[str, Any]:
    """Coerce stored/submitted policy to a valid shape. Unknown tiers are
    dropped; workspace_only is always on (it is the product); missing fields
    fall back to the safe default. Fails toward LESS sharing, never more."""
    base = default_policy()
    raw = raw or {}
    tiers = dict(base["tiers"])
    for tier, on in (raw.get("tiers") or {}).items():
        if tier in TIERS:
            tiers[tier] = bool(on)
    tiers[WORKSPACE_ONLY] = True  # non-negotiable: it is how the product works
    anonymization = raw.get("anonymization")
    return {
        "tiers": tiers,
        "anonymization": anonymization if anonymization in ANONYMIZATION else base["anonymization"],
        "derivative_data": ("shared_anonymized"
                            if (tiers[ANONYMIZED_PRIORS] or tiers[MODEL_IMPROVEMENT])
                            else "none_outside_workspace"),
        "knowledge_owner": "customer",
        "policy_version": POLICY_VERSION,
    }


def consent_diff(current: dict, proposed: dict) -> list[dict[str, Any]]:
    """The (tier, granted) changes between two policies — one ledger row each,
    so the append-only history records exactly what changed and nothing else."""
    changes = []
    cur, prop = normalize_policy(current)["tiers"], normalize_policy(proposed)["tiers"]
    for tier in TIERS:
        if cur.get(tier) != prop.get(tier):
            changes.append({"tier": tier, "granted": bool(prop.get(tier))})
    return changes


def current_consent(ledger_rows: list[dict]) -> dict[str, bool]:
    """Reduce the append-only ledger to the current grant state: the latest row
    per tier wins. Rows are expected newest-first (as stored)."""
    state = {WORKSPACE_ONLY: True, ANONYMIZED_PRIORS: False, MODEL_IMPROVEMENT: False}
    seen: set[str] = set()
    for row in ledger_rows:                      # newest first
        tier = row.get("tier")
        if tier in TIERS and tier not in seen:
            state[tier] = bool(row.get("granted"))
            seen.add(tier)
    state[WORKSPACE_ONLY] = True
    return state


# --------------------------------------------------------------- DB layer

def get_learning_policy(db, workspace_id: Optional[str]) -> dict[str, Any]:
    if not workspace_id:
        return default_policy()
    try:
        rows = db.table("workspaces").select("learning_policy").eq(
            "id", workspace_id).limit(1).execute().data or []
        return normalize_policy((rows[0].get("learning_policy") if rows else None))
    except Exception:
        return default_policy()


def set_learning_policy(db, *, org_id: str, workspace_id: str, proposed: dict,
                        actor_id: Optional[str], actor_email: str) -> dict[str, Any]:
    """Persist the workspace policy AND append one immutable consent row per
    changed tier. Consent is never overwritten — the ledger is the audit trail."""
    current = get_learning_policy(db, workspace_id)
    policy = normalize_policy(proposed)
    changes = consent_diff(current, policy)

    db.table("workspaces").update({"learning_policy": policy}).eq(
        "id", workspace_id).execute()

    for change in changes:
        db.table("learning_consent").insert({
            "org_id": org_id,
            "workspace_id": workspace_id,
            "tier": change["tier"],
            "policy": policy,
            "policy_version": POLICY_VERSION,
            "granted": change["granted"],
            "actor_id": actor_id,
            "actor_email": actor_email or "",
        }).execute()
    return {"policy": policy, "changes": changes, "policy_version": POLICY_VERSION}


def consent_history(db, org_id: str, workspace_id: Optional[str] = None,
                    limit: int = 100) -> list[dict]:
    try:
        q = db.table("learning_consent").select("*").eq("org_id", org_id)
        if workspace_id:
            q = q.eq("workspace_id", workspace_id)
        return q.order("created_at", desc=True).limit(limit).execute().data or []
    except Exception:
        return []
