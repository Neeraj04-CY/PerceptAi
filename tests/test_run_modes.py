"""Run controls (model + execution mode) — pinned.

Modes tune budgets and routing; honesty is not a dial. Private raises
egress, never lowers it. Unknown values never break a run."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

import run_modes  # noqa: E402


def test_modes_may_only_touch_budget_and_routing_keys():
    """THE pin: no mode may ever override verification or trust settings.
    If a key lands outside the allowlist, this fails loudly."""
    for name, overrides in {**run_modes.MODES, **run_modes.MODELS}.items():
        assert set(overrides) <= run_modes.ALLOWED_OVERRIDE_KEYS, name
    forbidden = {"critic_enabled", "approval_risk_threshold", "adaptive_perception"}
    assert not (run_modes.ALLOWED_OVERRIDE_KEYS & forbidden)


def test_model_and_mode_compose():
    out = run_modes.overrides_for("claude", "fast")
    assert out["model_provider"] == "anthropic"   # model wins routing
    assert out["find_retries"] == 2               # mode wins budgets


def test_unknown_values_fall_back_safely():
    assert run_modes.overrides_for("gpt-99", "warp-speed") == {}
    assert run_modes.overrides_for(None, None) == {}


def test_max_reliability_spends_more_than_fast():
    fast = run_modes.overrides_for(None, "fast")
    maxr = run_modes.overrides_for(None, "max_reliability")
    assert maxr["find_retries"] > fast["find_retries"]
    assert maxr["max_replans"] > fast["max_replans"]


def test_private_raises_egress_never_lowers():
    assert run_modes.egress_for({"mode": "allow"}, "private")["mode"] == "local_only"
    assert run_modes.egress_for(None, "private")["mode"] == "local_only"
    # A stricter workspace policy is the floor.
    assert run_modes.egress_for({"mode": "deny"}, "private")["mode"] == "deny"
    # Non-private modes leave workspace policy untouched.
    assert run_modes.egress_for({"mode": "redact"}, "fast") == {"mode": "redact"}
