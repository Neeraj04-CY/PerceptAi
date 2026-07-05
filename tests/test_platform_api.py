"""Platform-layer logic tests (Chapter Omega): RBAC, plans-as-data,
secrets crypto, workflow templates, event persistence and the platform
wire format. Pure logic only — no Supabase, no network, no screen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The api package uses flat, cwd-relative imports; append (not prepend) so
# nothing in the engine or stdlib is shadowed.
sys.path.append(str(Path(__file__).parent.parent / "api"))

from events_store import EventBuffer  # noqa: E402
from plans import PLAN_FALLBACKS, get_plan, monthly_limit  # noqa: E402
from rbac import ROLES, assignable_roles, can  # noqa: E402
from secrets_crypto import decrypt, derive_key, encrypt  # noqa: E402
from templates import TEMPLATES, get_template, render_instruction  # noqa: E402

from perceptai.events import EventType, TaskEvent  # noqa: E402
from perceptai.streaming import to_platform_sse  # noqa: E402


# ------------------------------------------------------------------ RBAC

class TestRbac:
    def test_owner_holds_everything(self):
        for permission in ("org.manage", "members.manage", "secrets.manage",
                           "approvals.decide", "execute", "view"):
            assert can("owner", permission)

    def test_role_hierarchy_is_monotonic(self):
        # Any permission a role holds, every more-privileged role holds too.
        from rbac import PERMISSIONS
        for permission in PERMISSIONS:
            held = [can(role, permission) for role in ROLES]  # owner..viewer
            # once a role loses the permission, all lesser roles lose it
            assert held == sorted(held, reverse=True)

    def test_viewer_is_read_only(self):
        assert can("viewer", "view")
        for permission in ("execute", "workflows.edit", "secrets.manage",
                           "members.manage", "approvals.decide"):
            assert not can("viewer", permission)

    def test_member_cannot_administrate(self):
        assert can("member", "execute")
        assert can("member", "workflows.edit")
        assert not can("member", "approvals.decide")
        assert not can("member", "policy.manage")

    def test_fails_closed(self):
        assert not can("superuser", "view")        # unknown role
        assert not can("owner", "not.a.permission")  # unknown permission

    def test_cannot_grant_above_own_role(self):
        assert "owner" not in assignable_roles("admin")
        assert assignable_roles("owner") == list(ROLES)
        assert assignable_roles("intruder") == []


# ----------------------------------------------------------------- plans

class _FakePlansDb:
    """Minimal chainable stub for db.table("plans").select(...).eq(...)."""

    def __init__(self, rows=None, fail=False):
        self._rows, self._fail = rows or [], fail

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("db down")
        return type("R", (), {"data": self._rows})()


class TestPlans:
    def test_fallback_without_db(self):
        plan = get_plan("scale")
        assert plan["monthly_executions"] == 999_999
        assert plan["limits"]["max_parallel"] == 8

    def test_unknown_plan_degrades_to_free(self):
        assert get_plan("platinum")["monthly_executions"] == \
            PLAN_FALLBACKS["free"]["monthly_executions"]

    def test_db_row_wins_over_fallback(self):
        db = _FakePlansDb(rows=[{"name": "Custom", "monthly_executions": 42,
                                 "limits": {"max_parallel": 3}}])
        plan = get_plan("builder", db)
        assert plan["monthly_executions"] == 42
        assert plan["limits"] == {"max_parallel": 3}

    def test_db_failure_degrades_not_raises(self):
        assert monthly_limit("builder", _FakePlansDb(fail=True)) == 10_000

    def test_every_fallback_has_workforce_limits(self):
        for plan in PLAN_FALLBACKS.values():
            for key in ("max_parallel", "max_work_orders",
                        "max_mission_duration_s", "max_total_cost"):
                assert key in plan["limits"]


# --------------------------------------------------------------- secrets

class TestSecretsCrypto:
    def test_roundtrip(self):
        key = derive_key("server-secret")
        assert decrypt(encrypt("pk_live_abc123", key), key) == "pk_live_abc123"

    def test_key_is_deterministic_per_secret(self):
        assert derive_key("a") == derive_key("a")
        assert derive_key("a") != derive_key("b")

    def test_wrong_key_raises_value_error(self):
        token = encrypt("value", derive_key("right"))
        with pytest.raises(ValueError):
            decrypt(token, derive_key("wrong"))

    def test_tampered_ciphertext_raises_value_error(self):
        key = derive_key("s")
        token = encrypt("value", key)
        with pytest.raises(ValueError):
            decrypt(token[:-4] + "AAAA", key)


# ------------------------------------------------------------- templates

class TestTemplates:
    def test_gallery_shape(self):
        assert len(TEMPLATES) >= 5
        ids = [t["id"] for t in TEMPLATES]
        assert len(ids) == len(set(ids))
        for t in TEMPLATES:
            assert t["mode"] in ("task", "mission")
            assert t["instruction"].strip()
            for var in t["variables"]:
                assert var["name"].isidentifier()

    def test_every_slot_is_declared(self):
        import re
        for t in TEMPLATES:
            declared = {v["name"] for v in t["variables"]}
            slots = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", t["instruction"]))
            assert slots <= declared, f"{t['id']} uses undeclared variables"

    def test_get_template(self):
        assert get_template("research-report")["mode"] == "mission"
        assert get_template("nope") is None

    def test_render_substitutes_values(self):
        t = get_template("extract-values")
        out = render_instruction(t["instruction"], t["variables"],
                                 {"source": "invoice.pdf", "fields": "total, date"})
        assert "invoice.pdf" in out and "total, date" in out
        assert "{{" not in out

    def test_render_uses_defaults(self):
        t = get_template("app-smoke-test")
        out = render_instruction(t["instruction"], t["variables"], {})
        assert "Notepad" in out

    def test_render_missing_required_raises(self):
        t = get_template("research-report")
        with pytest.raises(ValueError, match="topic"):
            render_instruction(t["instruction"], t["variables"], {})

    def test_render_undeclared_slot_raises(self):
        with pytest.raises(ValueError, match="mystery"):
            render_instruction("Do {{mystery}}", [], {})


# ---------------------------------------------------------- event store

class _InsertRecorder:
    def __init__(self, fail=False):
        self.batches: list[list] = []
        self._fail = fail

    def table(self, name):
        assert name == "events"
        return self

    def insert(self, rows):
        if self._fail:
            raise RuntimeError("db down")
        self.batches.append(rows)
        return self

    def execute(self):
        return self


class TestEventBuffer:
    @staticmethod
    def _event(seq, type_="log"):
        return {"type": type_, "seq": seq, "task_id": "t1",
                "timestamp": "2026-07-05T00:00:00Z", "payload": {"n": seq}}

    def test_cap_counts_dropped(self):
        buf = EventBuffer(max_events=3)
        for i in range(5):
            buf.collect(self._event(i + 1))
        assert len(buf.events) == 3 and buf.dropped == 2

    def test_rows_shape(self):
        buf = EventBuffer()
        buf.collect(self._event(7, "decision_made"))
        row = buf.rows("session", "abc")[0]
        assert row == {"owner_kind": "session", "owner_id": "abc", "seq": 7,
                       "type": "decision_made", "task_id": "t1",
                       "ts": "2026-07-05T00:00:00Z", "payload": {"n": 7}}

    def test_flush_chunks(self):
        buf = EventBuffer()
        for i in range(450):
            buf.collect(self._event(i + 1))
        db = _InsertRecorder()
        assert buf.flush(db, "mission", "m1")
        assert [len(b) for b in db.batches] == [200, 200, 50]

    def test_flush_failure_returns_false(self):
        buf = EventBuffer()
        buf.collect(self._event(1))
        assert buf.flush(_InsertRecorder(fail=True), "session", "s1") is False

    def test_empty_flush_is_success_without_insert(self):
        db = _InsertRecorder()
        assert EventBuffer().flush(db, "session", "s1")
        assert db.batches == []


# ------------------------------------------------------- platform wire

class TestPlatformWire:
    def test_full_fidelity_and_nested_payload(self):
        event = TaskEvent(type=EventType.MISSION_DECISION, session_id="s",
                          task_id="m1", seq=12,
                          payload={"decision": "dispatch", "type": "shadow-me"})
        wire = to_platform_sse(event)
        assert wire["type"] == "mission_decision"      # event field wins
        assert wire["seq"] == 12 and wire["task_id"] == "m1"
        assert wire["data"]["type"] == "shadow-me"     # payload never collides

    def test_every_event_type_is_representable(self):
        for event_type in EventType:
            wire = to_platform_sse(TaskEvent(type=event_type, session_id="s",
                                             task_id="t", seq=1))
            assert wire["type"] == event_type.value
