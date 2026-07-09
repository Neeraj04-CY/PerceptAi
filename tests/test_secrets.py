"""Sprint 7 — secure secrets-in-execution. Proves the whole value-flow
invariant: the value is typed only into a confirmed credential field, never
recorded anywhere, and zeroized when the run ends. Fully simulated."""
from __future__ import annotations

import json

from perceptai.contracts import (
    ActionType,
    BoundingBox,
    Observation,
    SourceType,
    Step,
    UIElement,
    WorldState,
)
from perceptai.control import ControlChannel
from perceptai.providers import PerceptionProvider
from perceptai.runtime import ExecutionEngine
from perceptai.secrets import (
    CachingSecretResolver,
    NullSecretResolver,
    mask_reference,
    parse_secret_reference,
)


def _step(action, description="", **params):
    return Step(action=ActionType(action), description=description, params=params)


# ------------------------------------------------------------ reference syntax

def test_parse_secret_reference():
    assert parse_secret_reference("{{secret:erp_pw}}") == "erp_pw"
    assert parse_secret_reference("  {{ secret: erp_pw }}  ") == "erp_pw"
    assert parse_secret_reference("login: {{secret:pw}}") is None   # never interpolated
    assert parse_secret_reference("just text") is None
    assert parse_secret_reference("") is None
    assert mask_reference("pw") == "{{secret:pw}}"


# ---------------------------------------------------------- resolver lifetime

class _FakeResolver(CachingSecretResolver):
    def __init__(self, values):
        super().__init__(available=list(values))
        self._values = values
        self.fetches = 0

    def _fetch(self, name):
        self.fetches += 1
        v = self._values.get(name)
        return v.encode("utf-8") if v is not None else None


def test_resolver_caches_and_zeroizes_on_purge():
    r = _FakeResolver({"pw": "hunter2"})
    assert r.resolve("pw") == "hunter2"
    assert r.resolve("pw") == "hunter2"
    assert r.fetches == 1                     # cached, not re-fetched
    buf = r._cache["pw"]
    r.purge()
    assert r._cache == {}                      # cache destroyed
    assert set(buf) == {0}                     # the underlying buffer was zeroized


def test_resolver_rejects_unknown_and_null_default():
    assert _FakeResolver({"pw": "x"}).resolve("other") is None
    assert NullSecretResolver().resolve("pw") is None
    assert NullSecretResolver().names() == []


# ------------------------------------------------------ field classification

def _world(elements):
    return WorldState(elements=elements)


def test_classify_secret_target():
    secure = UIElement(id="1", role="edit", name="pw", focused=True, secure=True)
    unsafe = UIElement(id="2", role="edit", name="user", focused=True, secure=False)
    other = UIElement(id="3", role="edit", name="x", focused=False)
    assert ExecutionEngine._classify_secret_target(_world([secure])) == "secure"
    assert ExecutionEngine._classify_secret_target(_world([unsafe])) == "unsafe"
    assert ExecutionEngine._classify_secret_target(_world([other])) == "unknown"
    assert ExecutionEngine._classify_secret_target(_world([])) == "unknown"


# --------------------------------------------------- full injection (simulated)

class _FieldProvider(PerceptionProvider):
    """Injects one field element so the classification guard has something to
    look at. Placed away from OCR text so it fuses as its own element."""
    name = "fake_field"
    source = SourceType.UIA
    cost = "free"

    def __init__(self, present=True, focused=True, secure=True):
        self._present, self._focused, self._secure = present, focused, secure

    def observe(self, frame):
        if not self._present:
            return []
        return [Observation(
            source=SourceType.UIA, role="edit", text="Password",
            bbox=BoundingBox(400, 400, 600, 430), confidence=1.0,
            attributes={"enabled": True, "focused": self._focused, "secure": self._secure})]


def _run_secret(harness, *, field, resolver, control=None, clear=False):
    session, fakes, events = harness(
        plans=[[_step("clear_type" if clear else "type", "enter the password",
                      text="{{secret:erp_pw}}")]],
    )
    session.secrets = resolver
    if control is not None:
        session.control = control
    session.world._providers.append(field)
    result = session.run("log in")
    return session, fakes, events, result


def _no_value_anywhere(events, result, value):
    blob = json.dumps([e.to_dict() for e in events]) + json.dumps(result.to_dict())
    return value not in blob


def test_secret_injected_into_credential_field_and_never_recorded(harness):
    r = _FakeResolver({"erp_pw": "hunter2"})
    session, fakes, events, result = _run_secret(
        harness, field=_FieldProvider(secure=True), resolver=r)

    assert fakes["actions"].typed == ["hunter2"]        # the real value was typed
    # the recorded step carries the masked reference, never the value
    typed_step = next(s for s in result.steps if s.step.action == ActionType.TYPE)
    assert typed_step.data == {"secret": "erp_pw", "masked": True}
    assert "secret_used" in [e.type.value for e in events]
    assert _no_value_anywhere(events, result, "hunter2")  # value in no event/report
    assert r._cache == {}                                 # zeroized + purged at run end


def test_secret_refused_on_non_credential_field(harness):
    r = _FakeResolver({"erp_pw": "hunter2"})
    _, fakes, events, result = _run_secret(
        harness, field=_FieldProvider(secure=False), resolver=r)
    assert fakes["actions"].typed == []                   # never typed into a visible field
    assert r.fetches == 0                                 # value never even fetched
    assert result.failure_type in ("secret_field_unsafe", "unknown")


def test_unclassified_field_without_approver_does_not_inject(harness):
    r = _FakeResolver({"erp_pw": "hunter2"})
    # default ControlChannel denies approval (no approver attached)
    _, fakes, events, result = _run_secret(
        harness, field=_FieldProvider(present=False), resolver=r, control=ControlChannel())
    assert fakes["actions"].typed == []
    assert "approval_requested" in [e.type.value for e in events]


def test_unavailable_secret_fails_honestly(harness):
    r = _FakeResolver({})  # no such secret
    _, fakes, events, result = _run_secret(
        harness, field=_FieldProvider(secure=True), resolver=r)
    assert fakes["actions"].typed == []
    assert result.failure_type in ("secret_unavailable", "unknown")
