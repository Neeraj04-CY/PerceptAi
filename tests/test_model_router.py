"""Chapter XV — Model Orchestration: the provider-agnostic, role-routed brain.

The redesign's whole promise is: frontier model for hard reasoning/grounding,
fast model for mechanical work, bring-your-own provider, and NEVER a regression
or an exception in the execution path. This pins all of it with fake providers —
no real model calls, deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from perceptai import llm as L  # noqa: E402
from perceptai.config import EngineConfig  # noqa: E402
from perceptai.egress import EgressGuard, EgressPolicy, EgressDenied  # noqa: E402


class FakeProvider:
    """Records calls; can be forced available/unavailable and made to fail."""
    def __init__(self, name, *, available=True, fail=False, reply='{"ok":1}'):
        self.name = name
        self._available = available
        self._fail = fail
        self._reply = reply
        self.text_calls = []
        self.vision_calls = []

    def available(self):
        return self._available

    def complete_text(self, prompt, model, max_tokens):
        self.text_calls.append((prompt, model, max_tokens))
        if self._fail:
            raise RuntimeError("provider down")
        return self._reply

    def complete_vision(self, image_b64, prompt, model, max_tokens):
        self.vision_calls.append((image_b64, prompt, model))
        if self._fail:
            raise RuntimeError("vision down")
        return self._reply


def _router(config=None, *, egress=None, providers=None):
    """A router with injected providers and routing rebuilt over them."""
    r = L.LLMClient(config or EngineConfig(groq_api_key="k"), egress=egress)
    if providers:
        r._providers = providers
        r._routing = L._build_routing(r._config, r._providers)
    return r


# ------------------------------------------------------------ role -> tier

def test_roles_map_to_the_right_tier():
    assert L._tier("plan") == L.REASON
    assert L._tier("heal") == L.REASON and L._tier("verify") == L.REASON
    assert L._tier("extract") == L.FAST and L._tier("report") == L.FAST
    assert L._tier("perceive") == L.VISION
    # an unknown role must get the CAPABLE model, never silently the cheap one
    assert L._tier("something_new") == L.REASON


# ------------------------------------------------- regression: groq path

def test_no_frontier_key_behaves_exactly_as_before():
    r = L.LLMClient(EngineConfig(groq_api_key="k"))  # no anthropic key
    for role in ("plan", "heal", "verify", "extract", "report"):
        assert r.provider_for(role) == "groq"
        assert r.model_for(role) == "llama-3.3-70b-versatile"
    assert r.provider_for("perceive") == "groq"
    assert r.model_for("perceive") == "meta-llama/llama-4-scout-17b-16e-instruct"


def test_frontier_unavailable_degrades_to_groq():
    # A key alone isn't enough — the provider must actually be usable. If the
    # frontier provider can't run (no SDK, bad key, import error), route to groq.
    providers = {"anthropic": FakeProvider("anthropic", available=False),
                 "groq": FakeProvider("groq", available=True)}
    r = _router(EngineConfig(groq_api_key="k", anthropic_api_key="sk-ant-x"), providers=providers)
    assert r.provider_for("plan") == "groq"


# --------------------------------------------- frontier-first when usable

def test_frontier_leads_reasoning_and_vision_when_available():
    cfg = EngineConfig(groq_api_key="k", anthropic_api_key="key",
                       anthropic_reason_model="claude-sonnet-5",
                       anthropic_fast_model="claude-haiku-4-5-20251001",
                       anthropic_vision_model="claude-sonnet-5")
    providers = {"anthropic": FakeProvider("anthropic", available=True),
                 "groq": FakeProvider("groq", available=True)}
    r = _router(cfg, providers=providers)
    assert r.provider_for("plan") == "anthropic" and r.model_for("plan") == "claude-sonnet-5"
    assert r.provider_for("extract") == "anthropic" and r.model_for("extract") == "claude-haiku-4-5-20251001"
    assert r.provider_for("perceive") == "anthropic" and r.model_for("perceive") == "claude-sonnet-5"

    r.complete_text("plan the thing", "plan")
    assert providers["anthropic"].text_calls and not providers["groq"].text_calls


def test_provider_override_forces_groq_even_with_frontier_present():
    cfg = EngineConfig(groq_api_key="k", anthropic_api_key="key", model_provider="groq")
    providers = {"anthropic": FakeProvider("anthropic", available=True),
                 "groq": FakeProvider("groq", available=True)}
    r = _router(cfg, providers=providers)
    assert r.provider_for("plan") == "groq"


# --------------------------------------------------- fallback + degradation

def test_falls_back_when_the_chosen_provider_fails():
    cfg = EngineConfig(groq_api_key="k", anthropic_api_key="key")
    providers = {"anthropic": FakeProvider("anthropic", available=True, fail=True),
                 "groq": FakeProvider("groq", available=True, reply='{"from":"groq"}')}
    r = _router(cfg, providers=providers)
    out = r.complete_text("plan", "plan")
    assert out == '{"from":"groq"}'                 # frontier failed -> groq answered
    assert providers["anthropic"].text_calls        # it was tried first
    assert providers["groq"].text_calls             # then fell back


def test_all_providers_dead_degrades_to_empty_never_raises():
    providers = {"anthropic": FakeProvider("anthropic", available=False),
                 "groq": FakeProvider("groq", available=True, fail=True)}
    r = _router(EngineConfig(groq_api_key="k", anthropic_api_key="key"), providers=providers)
    assert r.complete_text("x", "plan") == ""       # degrade, no exception
    parsed, raw = r.complete_json("x", "plan")
    assert parsed is None and raw == ""


# ------------------------------------------------- egress preserved (Ch. IX)

def test_deny_still_blocks_before_any_provider_is_touched():
    providers = {"anthropic": FakeProvider("anthropic", available=True),
                 "groq": FakeProvider("groq", available=True)}
    r = _router(EngineConfig(groq_api_key="k"),
                egress=EgressGuard(EgressPolicy.from_dict({"mode": "deny"})), providers=providers)
    with pytest.raises(EgressDenied):
        r.complete_text("secret screen", "plan")
    assert not providers["groq"].text_calls and not providers["anthropic"].text_calls
    assert r.calls == 0


def test_redaction_still_happens_before_the_bytes_leave():
    providers = {"groq": FakeProvider("groq", available=True),
                 "anthropic": FakeProvider("anthropic", available=False)}
    r = _router(EngineConfig(groq_api_key="k"),
                egress=EgressGuard(EgressPolicy.from_dict({"mode": "redact"})), providers=providers)
    r.complete_text("email bob@acme.com now", "plan")
    sent = providers["groq"].text_calls[0][0]
    assert "bob@acme.com" not in sent and "[REDACTED:email]" in sent


def test_vision_pixels_blocked_under_local_only_never_calls_a_provider():
    providers = {"groq": FakeProvider("groq", available=True),
                 "anthropic": FakeProvider("anthropic", available=False)}
    r = _router(EngineConfig(groq_api_key="k"),
                egress=EgressGuard(EgressPolicy.from_dict({"mode": "local_only"})), providers=providers)
    parsed, raw = r.complete_vision_json("BASE64", "describe", "perceive")
    assert parsed is None and raw == ""
    assert not providers["groq"].vision_calls


# --------------------------------------------------------------- misc

def test_explicit_model_override_is_honored():
    providers = {"groq": FakeProvider("groq", available=True), "anthropic": FakeProvider("anthropic", available=False)}
    r = _router(EngineConfig(groq_api_key="k"), providers=providers)
    r.complete_text("x", "plan", model="specific-model")
    assert providers["groq"].text_calls[0][1] == "specific-model"


def test_backcompat_string_construction_still_works():
    r = L.LLMClient("groq-key-only")
    assert r.provider_for("plan") == "groq"


def test_complete_json_parses_and_degrades():
    providers = {"groq": FakeProvider("groq", available=True, reply='{"a": 1}'),
                 "anthropic": FakeProvider("anthropic", available=False)}
    r = _router(EngineConfig(groq_api_key="k"), providers=providers)
    parsed, raw = r.complete_json("x", "plan")
    assert parsed == {"a": 1}
    # a non-JSON reply degrades to (None, raw), never raises
    providers["groq"]._reply = "not json at all"
    parsed, raw = r.complete_json("x", "plan")
    assert parsed is None and raw == "not json at all"


# --------------------------------------- multi-provider capability routing

def _all_provider_fakes(available):
    """Fakes for every provider; `available` is a set of provider names."""
    return {n: FakeProvider(n, available=(n in available))
            for n in ("groq", "anthropic", "openai", "gemini", "ollama")}


def test_auto_prefers_strongest_available_planner():
    from perceptai import model_catalog as mc
    # Only OpenAI + Groq configured -> auto picks OpenAI (higher in priority).
    r = _router(EngineConfig(groq_api_key="k", openai_api_key="o", model_provider="auto"),
                providers=_all_provider_fakes({"groq", "openai"}))
    assert r.provider_for("plan") == "openai"
    assert r.provider_for("extract") == "openai"        # fast tier too
    # With Gemini also present, Anthropic absent -> still OpenAI (priority order).
    r2 = _router(EngineConfig(groq_api_key="k", openai_api_key="o", gemini_api_key="g"),
                 providers=_all_provider_fakes({"groq", "openai", "gemini"}))
    assert r2.provider_for("plan") == "openai"


def test_auto_falls_to_groq_when_only_groq_available():
    r = _router(EngineConfig(groq_api_key="k"),
                providers=_all_provider_fakes({"groq"}))
    assert r.provider_for("plan") == "groq"
    assert r.model_for("plan") == "llama-3.3-70b-versatile"  # legacy model


def test_explicit_provider_override_wins():
    r = _router(EngineConfig(groq_api_key="k", openai_api_key="o", gemini_api_key="g",
                             model_provider="gemini"),
                providers=_all_provider_fakes({"groq", "openai", "gemini"}))
    assert r.provider_for("plan") == "gemini"


def test_text_only_provider_borrows_a_vision_provider():
    # Groq is the primary but its 70B reasoner is text-only; vision must borrow
    # the strongest available vision provider (openai here).
    r = _router(EngineConfig(groq_api_key="k", openai_api_key="o", model_provider="groq"),
                providers=_all_provider_fakes({"groq", "openai"}))
    assert r.provider_for("plan") == "groq"
    assert r.provider_for("perceive") in ("openai", "groq")  # a vision-capable one
    from perceptai import model_catalog as mc
    prof_ok = mc.profile(r.provider_for("perceive"), r.model_for("perceive"))
    assert prof_ok is not None and prof_ok.vision


def test_available_providers_is_honest():
    r = _router(EngineConfig(groq_api_key="k", openai_api_key="o"),
                providers=_all_provider_fakes({"groq", "openai"}))
    assert set(r.available_providers()) == {"groq", "openai"}
    assert r.active_provider() == "openai"


def test_reason_model_pin_overrides_the_catalog():
    r = _router(EngineConfig(groq_api_key="k", openai_api_key="o",
                             reason_model="gpt-5.6-custom"),
                providers=_all_provider_fakes({"groq", "openai"}))
    assert r.model_for("plan") == "gpt-5.6-custom"
    assert r.provider_for("plan") == "openai"
