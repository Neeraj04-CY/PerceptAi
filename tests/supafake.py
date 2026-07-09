"""A tiny in-memory Supabase-style fake for control-plane unit tests.

Just enough of the query-builder surface (select/insert/update, eq/neq/in_/
lt/not_.is_, order/limit) for the plane modules under test — no network, no
Postgres. Rows live in plain dicts per table name.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Optional


class FakeSupabase:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def table(self, name: str) -> "_Table":
        return _Table(self, name)

    def rpc(self, name: str, params: dict) -> "_Rpc":
        raise NotImplementedError(f"rpc '{name}' not faked")


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _NotProxy:
    def __init__(self, table: "_Table") -> None:
        self._table = table

    def is_(self, col: str, val: Any) -> "_Table":
        self._table._filters.append(("not_is", col, val))
        return self._table


class _Table:
    def __init__(self, db: FakeSupabase, name: str) -> None:
        self._db = db
        self._name = name
        self._filters: list[tuple] = []
        self._order: Optional[tuple[str, bool]] = None
        self._limit: Optional[int] = None
        self._op: Optional[tuple] = None  # ("insert", row) | ("update", patch)

    # ------------------------------------------------------------- builders
    def select(self, *_cols, **_kw) -> "_Table":
        return self

    def insert(self, row: Any) -> "_Table":
        self._op = ("insert", row)
        return self

    def update(self, patch: dict) -> "_Table":
        self._op = ("update", patch)
        return self

    def eq(self, col: str, val: Any) -> "_Table":
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val: Any) -> "_Table":
        self._filters.append(("neq", col, val))
        return self

    def in_(self, col: str, vals: list) -> "_Table":
        self._filters.append(("in", col, list(vals)))
        return self

    def lt(self, col: str, val: Any) -> "_Table":
        self._filters.append(("lt", col, val))
        return self

    @property
    def not_(self) -> _NotProxy:
        return _NotProxy(self)

    def order(self, col: str, desc: bool = False) -> "_Table":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_Table":
        self._limit = n
        return self

    # -------------------------------------------------------------- execute
    def _match(self, row: dict) -> bool:
        for op, col, val in self._filters:
            have = row.get(col)
            if op == "eq" and not (have == val or str(have) == str(val)):
                return False
            if op == "neq" and (have == val or str(have) == str(val)):
                return False
            if op == "in" and have not in val:
                return False
            if op == "lt" and not (have is not None and str(have) < str(val)):
                return False
            if op == "not_is" and val == "null" and have is None:
                return False
        return True

    def execute(self) -> _Result:
        rows = self._db.rows[self._name]
        if self._op and self._op[0] == "insert":
            payload = self._op[1]
            inserted = []
            for row in (payload if isinstance(payload, list) else [payload]):
                row = dict(row)
                row.setdefault("id", str(uuid.uuid4()))
                rows.append(row)
                inserted.append(row)
            return _Result(inserted)
        if self._op and self._op[0] == "update":
            patch = self._op[1]
            updated = []
            for row in rows:
                if self._match(row):
                    row.update(patch)
                    updated.append(row)
            return _Result(updated)
        matched = [r for r in rows if self._match(r)]
        if self._order:
            col, desc = self._order
            matched.sort(key=lambda r: str(r.get(col, "")), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return _Result(matched)
