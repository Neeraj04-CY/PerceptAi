"""OrgMemoryStore — the org's Business Memory, injected into the engine.

A decorator over the engine's local MemoryStore, installed at the
composition root (the executor builds it and hands it to AgentSession as
`memory=`). The engine is UNCHANGED and stays transport-independent: it
calls `recall_knowledge(...)` exactly as before, and receives the local
host's knowledge merged with the organization's compounding lessons —
corrections managers taught, recoveries other runs earned, application
quirks learned anywhere in the company.

This is the loop that makes the product harder to replace every week:
memory that never reached planning would be a notes app.
"""
from __future__ import annotations

from typing import Optional

import memory_service


class OrgMemoryStore:
    def __init__(self, base, db, org_id: str, limit: int = 6):
        self._base = base
        self._db = db
        self._org_id = org_id
        self._limit = limit

    def recall_knowledge(self, terms, limit: int = 10):
        local = []
        try:
            local = self._base.recall_knowledge(terms, limit) or []
        except Exception:
            local = []
        org = []
        try:
            org = memory_service.recall(self._db, self._org_id, list(terms or []),
                                        limit=self._limit)
        except Exception:
            org = []  # memory is best-effort; it never blocks a run
        # Org lessons lead: a manager's correction outranks a local cache.
        merged = org + [r for r in local if r not in org]
        return merged[:max(limit, self._limit)]

    def __getattr__(self, name):
        return getattr(self._base, name)


def build_org_memory(db, org_id: Optional[str]):
    """The executor's factory: org-scoped memory when the run belongs to an
    org, or None (engine default) when it doesn't."""
    if not org_id:
        return None
    try:
        from pathlib import Path
        from perceptai.memory import MemoryStore
        base = MemoryStore(Path.home() / ".perceptai" / "memory.db")
        return OrgMemoryStore(base, db, org_id)
    except Exception:
        return None
