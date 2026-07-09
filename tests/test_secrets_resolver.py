"""Sprint 7 Step 3 — LocalSecretResolver: scoped names, decrypt on fetch, and
the inherited zeroizing per-run cache. A tiny fake Supabase query builder; no
network, no real vault."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from config import config  # noqa: E402
from secrets_crypto import derive_key, encrypt  # noqa: E402
from secrets_resolver import LocalSecretResolver, build_local_resolver  # noqa: E402

KEY = derive_key(config.SECRETS_KEY)


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        rows = [r for r in self._rows
                if all(r.get(k) == v for k, v in self._filters.items())]
        return type("R", (), {"data": rows})


class _DB:
    def __init__(self, rows):
        self._rows = rows
        self.queries = 0

    def table(self, _name):
        self.queries += 1
        return _Query(self._rows)


def _rows():
    return [
        {"org_id": "o1", "workspace_id": "w1", "name": "ERP_PW",
         "ciphertext": encrypt("hunter2", KEY)},
        {"org_id": "o1", "workspace_id": None, "name": "ORG_TOKEN",
         "ciphertext": encrypt("orgtok", KEY)},
        {"org_id": "o1", "workspace_id": "w2", "name": "OTHER_WS",
         "ciphertext": encrypt("nope", KEY)},
    ]


def test_names_are_workspace_scoped_plus_org_wide():
    r = LocalSecretResolver(_DB(_rows()), org_id="o1", workspace_id="w1")
    assert r.names() == ["ERP_PW", "ORG_TOKEN"]      # not the w2-scoped secret


def test_resolves_and_decrypts_scoped_secret():
    r = LocalSecretResolver(_DB(_rows()), org_id="o1", workspace_id="w1")
    assert r.resolve("ERP_PW") == "hunter2"
    assert r.resolve("ORG_TOKEN") == "orgtok"
    assert r.resolve("OTHER_WS") is None              # out of scope -> unavailable


def test_purge_zeroizes_decrypted_value():
    r = LocalSecretResolver(_DB(_rows()), org_id="o1", workspace_id="w1")
    r.resolve("ERP_PW")
    buf = r._cache["ERP_PW"]
    r.purge()
    assert r._cache == {} and set(buf) == {0}


def test_no_org_means_no_resolver():
    assert build_local_resolver(_DB(_rows()), org_id=None, workspace_id="w1") is None
