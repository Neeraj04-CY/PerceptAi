"""Chapter IX Step 6 — Learning consent FOUNDATION.

Nothing consumes consent yet (organizational learning is not built). What is
tested here is the legal substrate the flywheel needs to exist before the first
contract: safe defaults, an explicit value-exchange per tier, and an append-only
consent ledger that an auditor can always reduce to "who granted what, when".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))
sys.path.append(str(Path(__file__).parent))

import learning as ln  # noqa: E402
from supafake import FakeSupabase  # noqa: E402


# ------------------------------------------------------------ safe defaults

def test_default_learning_policy_shares_nothing_outside_the_workspace():
    p = ln.default_policy()
    assert p["tiers"][ln.WORKSPACE_ONLY] is True        # the product itself
    assert p["tiers"][ln.ANONYMIZED_PRIORS] is False    # opt-in only
    assert p["tiers"][ln.MODEL_IMPROVEMENT] is False    # opt-in only
    assert p["derivative_data"] == "none_outside_workspace"
    assert p["knowledge_owner"] == "customer"


def test_normalize_fails_toward_less_sharing_not_more():
    # Unknown tier dropped; workspace_only forced on; bad anonymization -> strict.
    p = ln.normalize_policy({"tiers": {"exfiltrate_everything": True, ln.WORKSPACE_ONLY: False},
                             "anonymization": "none"})
    assert "exfiltrate_everything" not in p["tiers"]
    assert p["tiers"][ln.WORKSPACE_ONLY] is True
    assert p["anonymization"] == "strict"


def test_enabling_a_sharing_tier_flips_derivative_data():
    p = ln.normalize_policy({"tiers": {ln.ANONYMIZED_PRIORS: True}})
    assert p["derivative_data"] == "shared_anonymized"


def test_every_tier_declares_its_value_exchange():
    for tier in ln.TIERS:
        terms = ln.TIER_TERMS[tier]
        assert terms["grants"] and terms["benefit"]     # what you give AND what you get
        assert "shares_outside_workspace" in terms


# ------------------------------------------------------------- consent ledger

def test_consent_diff_is_one_row_per_changed_tier():
    current = ln.default_policy()
    proposed = ln.normalize_policy({"tiers": {ln.ANONYMIZED_PRIORS: True,
                                              ln.MODEL_IMPROVEMENT: True}})
    changes = ln.consent_diff(current, proposed)
    tiers = {c["tier"] for c in changes}
    assert tiers == {ln.ANONYMIZED_PRIORS, ln.MODEL_IMPROVEMENT}
    assert all(c["granted"] for c in changes)


def test_current_consent_reduces_the_append_only_ledger_latest_wins():
    # Stored newest-first: granted then later revoked -> current is revoked.
    ledger = [
        {"tier": ln.ANONYMIZED_PRIORS, "granted": False},   # newest
        {"tier": ln.ANONYMIZED_PRIORS, "granted": True},    # older
        {"tier": ln.MODEL_IMPROVEMENT, "granted": True},
    ]
    state = ln.current_consent(ledger)
    assert state[ln.ANONYMIZED_PRIORS] is False
    assert state[ln.MODEL_IMPROVEMENT] is True
    assert state[ln.WORKSPACE_ONLY] is True


def test_setting_policy_persists_and_appends_immutable_consent_rows():
    db = FakeSupabase()
    db.rows["workspaces"].append({"id": "ws-1", "org_id": "org-1"})

    result = ln.set_learning_policy(
        db, org_id="org-1", workspace_id="ws-1",
        proposed={"tiers": {ln.ANONYMIZED_PRIORS: True}},
        actor_id="u1", actor_email="a@b.co")

    assert result["policy"]["tiers"][ln.ANONYMIZED_PRIORS] is True
    consent = db.rows["learning_consent"]
    assert len(consent) == 1
    row = consent[0]
    assert row["tier"] == ln.ANONYMIZED_PRIORS and row["granted"] is True
    assert row["actor_id"] == "u1"
    assert row["policy_version"] == ln.POLICY_VERSION       # bound to the terms version
    # The workspace now carries the normalized policy.
    assert db.rows["workspaces"][0]["learning_policy"]["derivative_data"] == "shared_anonymized"


def test_an_unchanged_policy_appends_no_consent_rows():
    db = FakeSupabase()
    db.rows["workspaces"].append({"id": "ws-1", "org_id": "org-1"})
    ln.set_learning_policy(db, org_id="org-1", workspace_id="ws-1",
                           proposed=ln.default_policy(), actor_id="u1", actor_email="a@b.co")
    assert db.rows["learning_consent"] == []               # nothing changed -> nothing recorded


def test_revocation_is_recorded_as_history_not_a_deletion():
    db = FakeSupabase()
    db.rows["workspaces"].append({"id": "ws-1", "org_id": "org-1"})
    ln.set_learning_policy(db, org_id="org-1", workspace_id="ws-1",
                           proposed={"tiers": {ln.MODEL_IMPROVEMENT: True}},
                           actor_id="u1", actor_email="a@b.co")
    ln.set_learning_policy(db, org_id="org-1", workspace_id="ws-1",
                           proposed={"tiers": {ln.MODEL_IMPROVEMENT: False}},
                           actor_id="u2", actor_email="c@d.co")
    # Both the grant and the revoke are on the ledger — history is never rewritten.
    rows = [r for r in db.rows["learning_consent"] if r["tier"] == ln.MODEL_IMPROVEMENT]
    assert {r["granted"] for r in rows} == {True, False}
    assert len(rows) == 2


def test_get_learning_policy_normalizes_stored_data():
    db = FakeSupabase()
    db.rows["workspaces"].append({"id": "ws-1", "learning_policy": {"tiers": {ln.WORKSPACE_ONLY: False}}})
    # workspace_only can never actually be off — normalization guarantees it.
    assert ln.get_learning_policy(db, "ws-1")["tiers"][ln.WORKSPACE_ONLY] is True
    assert ln.get_learning_policy(db, None) == ln.default_policy()
