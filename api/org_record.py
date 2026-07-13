"""The Organizational Record — everything the company did, searchable.

Phase Three, Milestone 1. Two read-models over the SAME persisted tables
the rest of the platform writes (no new storage, no LLM, no synthesis):

- search(q): grounded, typed, linked hits across lessons, workflows,
  operations, approvals, attention and the audit trail — "what policies
  affect SAP?", "why does the invoice workflow fail?", "who approved
  erp_write?". Every hit points back at the row it came from.
- timeline(): one chronology of the organization — runs, decisions,
  lessons, escalations, administrative actions — merged and ordered.

Sources that don't exist yet on an unmigrated database are skipped and
NAMED in the response; results never fabricate and never 500.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_STOPWORDS = {"the", "a", "an", "and", "or", "to", "in", "on", "of", "for",
              "with", "why", "who", "what", "how", "does", "do", "is", "are"}
_MAX_PER_SOURCE = 60
_SNIPPET = 140


def _terms(q: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+", (q or "").lower())
            if len(t) >= 2 and t not in _STOPWORDS][:8]


def _score(text: str, title: str, terms: list[str]) -> float:
    text_l, title_l = text.lower(), title.lower()
    hits = sum(1 for t in terms if t in text_l)
    title_hits = sum(1 for t in terms if t in title_l)
    if hits + title_hits == 0:
        return 0.0
    return hits + 2.0 * title_hits


def _snippet(text: str, terms: list[str]) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    lower = text.lower()
    for t in terms:
        at = lower.find(t)
        if at >= 0:
            start = max(0, at - 40)
            return ("…" if start else "") + text[start:start + _SNIPPET] + \
                   ("…" if start + _SNIPPET < len(text) else "")
    return text[:_SNIPPET] + ("…" if len(text) > _SNIPPET else "")


# ------------------------------------------------------------------ sources
# Each source: (name, fetch(db, org_id) -> rows, to_hit(row) -> dict|None).
# `to_hit` returns {type, id, title, body, when, status, ref} — `body` is
# what gets snippeted/scored alongside the title.

def _sources() -> list[tuple[str, Callable, Callable]]:
    def lessons(db, org_id):
        return db.table("business_memory").select("*").eq("org_id", org_id).eq(
            "archived", False).limit(_MAX_PER_SOURCE * 3).execute().data or []

    def lesson_hit(r):
        return {"type": "lesson", "id": r.get("id"),
                "title": f"Lesson: {r.get('subject', '')}",
                "body": f"{r.get('lesson', '')} {r.get('scope', '')} {r.get('kind', '')}",
                "when": r.get("last_reinforced_at") or r.get("created_at"),
                "status": f"{r.get('source', '')} · reinforced ×{r.get('times_reinforced', 1)}",
                "ref": {"page": "knowledge"}}

    def workflows(db, org_id):
        return db.table("workflows").select(
            "id,name,instruction,status,updated_at").eq(
            "org_id", org_id).limit(_MAX_PER_SOURCE * 2).execute().data or []

    def workflow_hit(r):
        return {"type": "workflow", "id": r.get("id"),
                "title": r.get("name", "Workflow"),
                "body": r.get("instruction", ""),
                "when": r.get("updated_at"),
                "status": r.get("status", ""),
                "ref": {"page": "workflow", "id": r.get("id")}}

    def sessions(db, org_id):
        return db.table("sessions").select(
            "id,instruction,status,created_at,result,workflow_id").eq(
            "org_id", org_id).order("created_at", desc=True).limit(
            _MAX_PER_SOURCE * 5).execute().data or []

    def session_hit(r):
        failure = str(((r.get("result") or {}) or {}).get("failure_type") or "")
        return {"type": "operation", "id": r.get("id"),
                "title": str(r.get("instruction", ""))[:90],
                "body": f"{r.get('instruction', '')} {failure}",
                "when": r.get("created_at"),
                "status": r.get("status", "") + (f" · {failure.replace('_', ' ')}" if failure else ""),
                "ref": {"page": "operation", "id": r.get("id")}}

    def approvals(db, org_id):
        return db.table("approvals").select("*").eq("org_id", org_id).order(
            "created_at", desc=True).limit(_MAX_PER_SOURCE * 2).execute().data or []

    def approval_hit(r):
        return {"type": "approval", "id": r.get("id"),
                "title": f"Approval: {r.get('capability', '')}",
                "body": f"{r.get('objective', '')} {r.get('reason', '')} {r.get('capability', '')}",
                "when": r.get("decided_at") or r.get("created_at"),
                "status": r.get("status", ""),
                "ref": {"page": "approvals"}}

    def attention(db, org_id):
        return db.table("attention_items").select("*").eq(
            "org_id", org_id).order("created_at", desc=True).limit(
            _MAX_PER_SOURCE).execute().data or []

    def attention_hit(r):
        return {"type": "attention", "id": r.get("id"),
                "title": str(r.get("title", ""))[:90],
                "body": f"{r.get('title', '')} {r.get('kind', '')}",
                "when": r.get("created_at"),
                "status": f"{r.get('kind', '')} · {r.get('status', '')}",
                "ref": {"page": "operation", "id": r.get("session_id")}
                if r.get("session_id") else {"page": "knowledge"}}

    def audit(db, org_id):
        return db.table("audit_log").select("*").eq("org_id", org_id).order(
            "created_at", desc=True).limit(_MAX_PER_SOURCE * 2).execute().data or []

    def audit_hit(r):
        return {"type": "audit", "id": r.get("id"),
                "title": f"{r.get('action', '')}: {r.get('target', '')}"[:90],
                "body": f"{r.get('action', '')} {r.get('target', '')} {r.get('actor_email', '')}",
                "when": r.get("created_at"),
                "status": r.get("actor_email", ""),
                "ref": {"page": "organization"}}

    return [("lessons", lessons, lesson_hit),
            ("workflows", workflows, workflow_hit),
            ("operations", sessions, session_hit),
            ("approvals", approvals, approval_hit),
            ("attention", attention, attention_hit),
            ("audit", audit, audit_hit)]


# ------------------------------------------------------------------- search

def search(db, org_id: str, q: str, limit: int = 20) -> dict:
    """Grounded organizational search. Ranked by term relevance (title
    weighted) with recency as the tiebreaker; every hit links back to its
    row. Empty query returns nothing (use timeline for chronology)."""
    terms = _terms(q)
    if not terms:
        return {"query": q, "hits": [], "sources_skipped": [],
                "note": "Give me at least one meaningful word."}

    hits: list[tuple[float, str, dict]] = []
    skipped: list[str] = []
    for name, fetch, to_hit in _sources():
        try:
            rows = fetch(db, org_id)
        except Exception:
            skipped.append(name)
            continue
        for r in rows:
            h = to_hit(r)
            if h is None:
                continue
            s = _score(str(h.pop("body", "")), str(h.get("title", "")), terms)
            if s <= 0:
                continue
            h["snippet"] = _snippet(str(r.get("lesson") or r.get("instruction")
                                        or r.get("objective") or r.get("title")
                                        or r.get("target") or ""), terms)
            when = str(h.get("when") or "")
            hits.append((s, when, h))

    hits.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return {"query": q,
            "hits": [dict(h, relevance=round(s, 1)) for s, _w, h in hits[:limit]],
            "sources_skipped": skipped,
            "note": ("Some sources need migrations: " + ", ".join(skipped)
                     + " — run api/migrations/verify_schema.py") if skipped else ""}


# ------------------------------------------------------------------ timeline

def timeline(db, org_id: str, limit: int = 50) -> dict:
    """One chronology of the organization, merged from every source and
    ordered newest first. The history of the company, on one axis."""
    entries: list[dict] = []
    skipped: list[str] = []
    for name, fetch, to_hit in _sources():
        try:
            rows = fetch(db, org_id)
        except Exception:
            skipped.append(name)
            continue
        for r in rows:
            h = to_hit(r)
            if h is None or not h.get("when"):
                continue
            h.pop("body", None)
            entries.append(h)
    entries.sort(key=lambda e: str(e.get("when") or ""), reverse=True)
    return {"entries": entries[:max(1, min(limit, 200))],
            "sources_skipped": skipped,
            "note": ("Some sources need migrations: " + ", ".join(skipped)
                     + " — run api/migrations/verify_schema.py") if skipped else ""}
