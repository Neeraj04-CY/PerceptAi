"""Chapter IX Step 3 — Data egress controls.

A company must always be able to answer, from the record: what left the machine,
why it left, where it went, what model received it, and which policy allowed it.
Policy is data; enforcement is one checkpoint (llm.py); the vision provider
additionally minimizes (never encodes a screenshot it may not send).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from perceptai import egress as eg  # noqa: E402
from perceptai.llm import LLMClient  # noqa: E402


# ------------------------------------------------------------------ policy

def test_default_policy_allows_everything():
    p = eg.EgressPolicy.from_dict(None)
    assert p.mode == eg.ALLOW and p.allows_text and p.allows_pixels and not p.redacts


def test_local_only_blocks_pixels_but_not_text():
    """The mode a Fortune 500 DLP team actually asks for: screenshots of the
    ERP never leave; the agent keeps working on local perception."""
    p = eg.EgressPolicy.from_dict({"mode": "local_only"})
    assert p.allows_text is True
    assert p.allows_pixels is False
    assert "never leave this machine" in p.reason(eg.PIXELS)


def test_deny_blocks_both():
    p = eg.EgressPolicy.from_dict({"mode": "deny"})
    assert p.allows_text is False and p.allows_pixels is False


def test_redact_mode_defaults_to_every_class():
    p = eg.EgressPolicy.from_dict({"mode": "redact"})
    assert p.redacts and "email" in p.redact_classes and "credit_card" in p.redact_classes


def test_unknown_mode_fails_to_the_documented_default_not_a_bricked_fleet():
    """A typo in policy must not silently deny every run in the org. The honest
    control for 'nothing leaves' is an explicit `deny`, which is stored."""
    assert eg.EgressPolicy.from_dict({"mode": "DENYY"}).mode == eg.ALLOW
    assert eg.EgressPolicy.from_dict({"mode": "DENY"}).mode == eg.DENY   # case-insensitive


def test_policy_round_trips_as_data():
    raw = {"mode": "redact", "redact": ["email"], "custom_patterns": [r"ACME-\d+"]}
    assert eg.EgressPolicy.from_dict(raw).to_dict() == raw


# --------------------------------------------------------------- redaction

def test_redaction_removes_sensitive_spans_deterministically():
    text = "Contact bob@acme.com or 4111 1111 1111 1111, ssn 123-45-6789, key sk-abcdefghijklmnopqr"
    out, n = eg.redact(text, ("email", "credit_card", "ssn", "api_key"))
    assert "bob@acme.com" not in out and "4111" not in out
    assert "123-45-6789" not in out and "sk-abcdefghijklmnopqr" not in out
    assert n == 4
    assert eg.redact(text, ("email",))[0] == eg.redact(text, ("email",))[0]  # stable


def test_redaction_preserves_ordinary_ui_text():
    text = "Click Save. Invoice INV-2026-014 total 41.20"
    out, n = eg.redact(text, eg._REDACTOR_NAMES)
    assert n == 0 and out == text     # a redactor that eats the UI is an outage


def test_custom_pattern_and_a_broken_one():
    out, n = eg.redact("badge ACME-9931", (), (r"ACME-\d+",))
    assert "ACME-9931" not in out and n == 1
    # An invalid customer regex must never break execution.
    out, n = eg.redact("x", (), (r"[unclosed",))
    assert out == "x" and n == 0


# ------------------------------------------------------------------- guard

def _guard(mode, **kw):
    events = []
    guard = eg.EgressGuard(eg.EgressPolicy.from_dict({"mode": mode, **kw}), emit=events.append)
    return guard, events


def test_allowed_text_is_recorded_with_the_five_answers():
    guard, events = _guard("allow")
    out, decision = guard.text("hello", model="llama-3.3-70b", purpose="plan")
    assert out == "hello" and decision.allowed
    (recorded,) = events
    assert recorded.kind == "text"           # WHAT
    assert recorded.reason                   # WHY
    assert recorded.model == "llama-3.3-70b"  # WHERE / WHICH MODEL
    assert recorded.purpose == "plan"
    assert recorded.mode == "allow"          # WHICH POLICY
    assert recorded.size == 5


def test_denied_text_raises_and_is_recorded():
    guard, events = _guard("deny")
    with pytest.raises(eg.EgressDenied) as e:
        guard.text("secret screen contents", model="m", purpose="plan")
    assert e.value.decision.allowed is False
    assert events[0].allowed is False


def test_pixels_blocked_under_local_only_never_raise():
    """Vision degrades; the local providers carry the run. Pixels remain the
    perception floor — on this machine."""
    guard, events = _guard("local_only")
    decision = guard.pixels(model="vision-model", purpose="perceive", size=90000)
    assert decision.allowed is False and decision.size == 90000
    assert "never leave this machine" in decision.reason
    assert guard.allows_text is True


def test_guard_redacts_outbound_text_and_counts_it():
    guard, events = _guard("redact")
    out, decision = guard.text("mail bob@acme.com", model="m", purpose="plan")
    assert "bob@acme.com" not in out and decision.redactions == 1


def test_allowed_decisions_dedup_but_blocked_ones_always_speak():
    guard, events = _guard("allow")
    for _ in range(5):
        guard.text("x", model="m", purpose="plan")
    assert len(events) == 1                    # a 30-step run emits one row

    guard, events = _guard("local_only")
    for _ in range(3):
        guard.pixels(model="m", purpose="perceive")
    assert len(events) == 3                    # every refusal is news


def test_events_never_carry_content():
    guard, events = _guard("allow")
    guard.text("SUPER SENSITIVE ERP SCREEN", model="m", purpose="plan")
    body = str(events[0].to_dict())
    assert "SENSITIVE" not in body             # metadata only, never content
    assert events[0].size == len("SUPER SENSITIVE ERP SCREEN")


def test_emit_failure_never_breaks_execution():
    def boom(_):
        raise RuntimeError("bus down")
    guard = eg.EgressGuard(eg.ALLOW_ALL, emit=boom)
    out, _ = guard.text("x", model="m", purpose="plan")
    assert out == "x"


# --------------------------------------------- the ONE checkpoint: llm.py

class _FakeGroq:
    def __init__(self):
        self.sent = []
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, model, messages, max_tokens):
        self.sent.append(messages)
        return type("R", (), {"choices": [type("C", (), {
            "message": type("M", (), {"content": '{"ok": true}'})()})()]})()


def _client(mode) -> tuple[LLMClient, _FakeGroq]:
    client = LLMClient("key", egress=eg.EgressGuard(eg.EgressPolicy.from_dict({"mode": mode})))
    fake = _FakeGroq()
    # Inject the fake behind the Groq provider — the egress checkpoint still
    # gates every send the same way; only the transport is faked.
    client._providers["groq"]._client = fake
    return client, fake


def test_denied_prompt_never_touches_the_network():
    client, fake = _client("deny")
    with pytest.raises(eg.EgressDenied):
        client.complete_text("screen contents", model="m")
    assert fake.sent == [] and client.calls == 0


def test_screenshot_never_leaves_under_local_only():
    client, fake = _client("local_only")
    parsed, raw = client.complete_vision_json("BASE64PIXELS", "describe", model="vision")
    assert parsed is None and raw == ""
    assert fake.sent == [] and client.calls == 0   # no network call at all


def test_text_still_flows_under_local_only():
    client, fake = _client("local_only")
    assert client.complete_text("plan this", model="m") == '{"ok": true}'
    assert len(fake.sent) == 1


def test_redaction_happens_before_the_bytes_leave():
    client, fake = _client("redact")
    client.complete_text("email bob@acme.com now", model="m")
    sent = str(fake.sent[0])
    assert "bob@acme.com" not in sent and "[REDACTED:email]" in sent


def test_default_client_has_no_policy_and_sends_everything():
    client = LLMClient("key")
    fake = _FakeGroq()
    client._providers["groq"]._client = fake
    client.complete_text("anything", model="m")
    assert len(fake.sent) == 1


# --------------------------------- data minimization at the vision provider

def test_vision_provider_is_unavailable_when_pixels_may_not_leave():
    """Not a second gate — minimization. The screenshot is never read, never
    base64-encoded, never held in memory on its way out."""
    from perceptai.config import EngineConfig
    from perceptai.providers import VisionProvider

    llm = LLMClient("k", egress=eg.EgressGuard(eg.EgressPolicy.from_dict({"mode": "local_only"})))
    assert VisionProvider(EngineConfig(), llm).available() is False

    llm_allowed = LLMClient("k")
    assert VisionProvider(EngineConfig(), llm_allowed).available() is True


# ------------------------------------------------- honest up-front refusal

def test_deny_policy_refuses_the_run_before_contacting_any_model(tmp_path):
    from perceptai.simulation import build_simulated_session

    session, _fakes, _events = build_simulated_session(plans=[[]], workspace=tmp_path)
    session.egress = eg.EgressGuard(eg.EgressPolicy.from_dict({"mode": "deny"}))
    result = session.run("do something")

    assert result.status.value == "failed"
    assert "denies sending screen observations" in result.summary
    assert result.errors and "denies all egress" in result.errors[0]
