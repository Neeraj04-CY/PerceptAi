"""The Organizational Graph — the business as a connected system.

Milestone D. Workflows, departments, applications, capabilities, failure
modes and lessons are NODES; measured operational history provides the
EDGES (runs, failures, approvals, lesson scopes, template lineage).
Discoveries emerge from RELATIONSHIPS rather than isolated statistics:
the same obstacle across departments is a systemic problem; the same
instruction in two departments is duplicated work; a success-rate gap on
a shared application is transferable learning.

Rules (identical to Workforce Intelligence, enforced by tests):
- Built deterministically from measured rows. NO LLM anywhere here.
- Every discovery carries evidence, a measured confidence, the affected
  departments, its business impact in measured terms, and one
  recommended action. Reproducible from the same tables it came from.
- Insufficient evidence is silence, never speculation.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

from templates import PACKS, TEMPLATES

ANALYSIS_DAYS = 30
MIN_RUNS_FOR_RATE = 3          # a success rate below this sample stays silent
DUPLICATE_SIMILARITY = 0.78    # instruction similarity that means "same work"
MIN_SYSTEMIC_WORKFLOWS = 2     # same obstacle across at least this many workflows
TRANSFER_GAP = 0.35            # success-rate gap worth transferring lessons over
MIN_CROSS_WS_APPROVALS = 6     # per workspace before "redundant across org"

_DEPARTMENT_OF_TEMPLATE = {t["name"].lower(): t["pack"] for t in TEMPLATES}
_PACK_NAME = {p["id"]: p["name"] for p in PACKS}
_APPS_OF_TEMPLATE = {t["name"].lower(): [a for a in (t.get("apps") or [])
                                         if "any" not in a.lower()]
                     for t in TEMPLATES}
_KNOWN_APPS = sorted({a.lower() for apps in _APPS_OF_TEMPLATE.values() for a in apps})


def _cutoff_iso(days: int = ANALYSIS_DAYS) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ------------------------------------------------------------------ graph

def build_graph(db, org_id: str) -> dict:
    """Nodes + weighted edges from measured rows. The substrate every
    discovery (and every future recommendation surface) reads."""
    try:
        workflows = db.table("workflows").select(
            "id,name,instruction,status").eq("org_id", org_id).limit(
            200).execute().data or []
        sessions = db.table("sessions").select(
            "id,workflow_id,status,instruction,result,created_at"
        ).eq("org_id", org_id).order("created_at", desc=True).limit(
            500).execute().data or []
    except Exception as e:
        return {"nodes": [], "edges": [], "error": (
            f"operational schema incomplete — run api/migrations/verify_schema.py ({e})")}

    cutoff = _cutoff_iso()
    sessions = [s for s in sessions if str(s.get("created_at") or "") >= cutoff]

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(node_id: str, node_type: str, label: str, **attrs) -> str:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label, **attrs}
        return node_id

    def edge(src: str, rel: str, dst: str, weight: float = 1.0, **attrs) -> None:
        edges.append({"src": src, "rel": rel, "dst": dst,
                      "weight": round(weight, 3), **attrs})

    # Workflows -> departments (template lineage) and applications.
    for wf in workflows:
        wf_node = node(f"workflow:{wf['id']}", "workflow", wf.get("name", ""))
        dept = _DEPARTMENT_OF_TEMPLATE.get(str(wf.get("name", "")).lower(), "general")
        dept_node = node(f"department:{dept}", "department",
                         _PACK_NAME.get(dept, "General"))
        edge(wf_node, "BELONGS_TO", dept_node)
        for app in _apps_of(wf):
            app_node = node(f"application:{app}", "application", app)
            edge(wf_node, "TOUCHES", app_node)

    # Runs -> workflow stats + failure modes.
    runs_by_wf: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        if s.get("workflow_id"):
            runs_by_wf[s["workflow_id"]].append(s)
    for wf_id, runs in runs_by_wf.items():
        wf_node = f"workflow:{wf_id}"
        if wf_node not in nodes:
            wf_node = node(wf_node, "workflow", _label(runs))
        verified = sum(1 for r in runs if r.get("status") == "completed")
        nodes[wf_node]["runs"] = len(runs)
        nodes[wf_node]["verified_rate"] = round(verified / len(runs), 3)
        for failure, count in _failures(runs).items():
            f_node = node(f"failure:{failure}", "failure_mode", failure)
            edge(wf_node, "FAILS_WITH", f_node, weight=count, count=count)

    # Approvals -> capabilities.
    try:
        approvals = db.table("approvals").select(
            "capability,status,workspace_id,created_at").eq(
            "org_id", org_id).order("created_at", desc=True).limit(
            500).execute().data or []
    except Exception:
        approvals = []
    per_cap: dict[str, list[dict]] = defaultdict(list)
    for a in approvals:
        per_cap[str(a.get("capability") or "")].append(a)
    for cap, rows in per_cap.items():
        if not cap:
            continue
        cap_node = node(f"capability:{cap}", "capability", cap)
        approved = sum(1 for r in rows if r.get("status") == "approved")
        denied = sum(1 for r in rows if r.get("status") == "denied")
        nodes[cap_node]["approved"] = approved
        nodes[cap_node]["denied"] = denied
        nodes[cap_node]["workspaces"] = len({r.get("workspace_id") for r in rows})

    # Lessons -> applications (Business Memory scopes).
    try:
        lessons = db.table("business_memory").select("*").eq(
            "org_id", org_id).eq("archived", False).limit(200).execute().data or []
    except Exception:
        lessons = []
    for lesson in lessons:
        l_node = node(f"lesson:{lesson.get('id')}", "lesson",
                      str(lesson.get("lesson", ""))[:80],
                      reinforced=lesson.get("times_reinforced", 1),
                      source=lesson.get("source"))
        scope = str(lesson.get("scope") or "")
        if scope.startswith("app:"):
            app_node = node(f"application:{scope[4:]}", "application", scope[4:])
            edge(l_node, "APPLIES_TO", app_node)

    return {"nodes": list(nodes.values()), "edges": edges,
            "period_days": ANALYSIS_DAYS,
            "counts": _counts(nodes, edges)}


def _counts(nodes: dict, edges: list) -> dict:
    by_type: dict[str, int] = defaultdict(int)
    for n in nodes.values():
        by_type[n["type"]] += 1
    return {"nodes": len(nodes), "edges": len(edges), "by_type": dict(by_type)}


def _apps_of(wf: dict) -> list[str]:
    """Applications a workflow touches: template lineage first, then known
    app names present in the instruction text. Lowercased node keys."""
    apps = [a.lower() for a in _APPS_OF_TEMPLATE.get(str(wf.get("name", "")).lower(), [])]
    text = str(wf.get("instruction") or "").lower()
    apps += [a for a in _KNOWN_APPS if a and a in text and a not in apps]
    return sorted(set(apps))


def _label(runs: list[dict]) -> str:
    text = str(runs[0].get("instruction") or "workflow")
    return (text[:60] + "…") if len(text) > 60 else text


def _failures(runs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for r in runs:
        ft = str(((r.get("result") or {}) or {}).get("failure_type") or "").strip()
        if ft:
            counts[ft.replace("_", " ")] += 1
    return dict(counts)


# ------------------------------------------------------------- discoveries

def discoveries(db, org_id: str) -> dict:
    """Business discoveries from measured relationships. Every entry:
    kind, headline, detail, evidence, confidence (sample-size based),
    affected_departments, business_impact, recommended_action."""
    graph = build_graph(db, org_id)
    if graph.get("error"):
        return {"period_days": ANALYSIS_DAYS, "discoveries": [],
                "coverage": {"sufficient": False, "note": graph["error"]}}

    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    found: list[dict] = []
    found += _duplicated_work(db, org_id, nodes, edges)
    found += _systemic_obstacles(nodes, edges)
    found += _learning_transfer(nodes, edges)
    found += _redundant_approvals(nodes)

    rank = {"high": 0, "medium": 1, "info": 2}
    found.sort(key=lambda d: (rank.get(d["severity"], 3), -d["confidence"]))
    return {
        "period_days": ANALYSIS_DAYS,
        "coverage": {
            "sufficient": bool(nodes),
            "note": "" if nodes else ("No graded relationships yet — discoveries "
                                      "emerge as real work accumulates."),
        },
        "discoveries": found,
    }


def _confidence(n: int, k: int = 4) -> float:
    """Sample-size confidence: grows with evidence, never reaches 1."""
    return round(min(0.95, n / (n + k)), 2)


def _dept_of(wf_node_id: str, edges: list, nodes: dict) -> str:
    for e in edges:
        if e["src"] == wf_node_id and e["rel"] == "BELONGS_TO":
            return nodes.get(e["dst"], {}).get("label", "General")
    return "General"


def _duplicated_work(db, org_id: str, nodes: dict, edges: list) -> list[dict]:
    """Two workflows whose instructions are near-identical are the same job
    hired twice — merge them (or make one canonical) so the track record
    and lessons compound in one place instead of splitting."""
    try:
        workflows = db.table("workflows").select(
            "id,name,instruction").eq("org_id", org_id).limit(100).execute().data or []
    except Exception:
        return []
    out = []
    for i in range(len(workflows)):
        for j in range(i + 1, len(workflows)):
            a, b = workflows[i], workflows[j]
            ia = re.sub(r"\s+", " ", str(a.get("instruction") or "").lower()).strip()
            ib = re.sub(r"\s+", " ", str(b.get("instruction") or "").lower()).strip()
            if len(ia) < 20 or len(ib) < 20:
                continue
            sim = SequenceMatcher(None, ia[:400], ib[:400]).ratio()
            if sim < DUPLICATE_SIMILARITY:
                continue
            da = _dept_of(f"workflow:{a['id']}", edges, nodes)
            db_ = _dept_of(f"workflow:{b['id']}", edges, nodes)
            out.append({
                "kind": "duplicated_work", "severity": "medium",
                "headline": "Two roles are doing the same job",
                "detail": (f"“{a.get('name')}” and “{b.get('name')}” have "
                           f"{round(sim * 100)}% identical briefs"
                           + (f" across {da} and {db_}" if da != db_ else "")
                           + ". Merging them pools the runs, the track record and "
                             "the lessons into one stronger operator."),
                "evidence": {"workflow_ids": [a["id"], b["id"]],
                             "similarity": round(sim, 3)},
                "confidence": round(sim, 2),
                "affected_departments": sorted({da, db_}),
                "business_impact": "Split track records slow autonomy: each copy "
                                   "must earn trust separately.",
                "recommended_action": "Merge into one workflow (or archive one) so "
                                      "evidence compounds in a single place.",
            })
    return out


def _systemic_obstacles(nodes: dict, edges: list) -> list[dict]:
    """The same failure mode across multiple workflows that touch the same
    application: the obstacle is the APPLICATION, not any one workflow."""
    fails_by_failure: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        if e["rel"] == "FAILS_WITH":
            fails_by_failure[e["dst"]].append(e)
    touches: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["rel"] == "TOUCHES":
            touches[e["src"]].add(e["dst"])

    out = []
    for failure_node, hits in fails_by_failure.items():
        wfs = [h["src"] for h in hits]
        if len(wfs) < MIN_SYSTEMIC_WORKFLOWS:
            continue
        shared_apps = set.intersection(*(touches[w] or {"application:?"} for w in wfs)) \
            if all(touches.get(w) for w in wfs) else set()
        total = int(sum(h.get("count", h["weight"]) for h in hits))
        depts = sorted({_dept_of(w, edges, nodes) for w in wfs})
        failure = nodes.get(failure_node, {}).get("label", "a failure")
        app_label = nodes.get(next(iter(shared_apps)), {}).get("label") if shared_apps else None
        out.append({
            "kind": "systemic_obstacle", "severity": "high",
            "headline": (f"'{failure}' is systemic"
                         + (f" in {app_label}" if app_label else " across the workforce")),
            "detail": (f"{len(wfs)} different responsibilities hit '{failure}' "
                       f"{total} times this period"
                       + (f", all inside {app_label}" if app_label else "")
                       + ". One taught lesson or policy fixes it everywhere at once — "
                         "this is not a per-workflow problem."),
            "evidence": {"failure": failure, "workflows": len(wfs),
                         "occurrences": total,
                         "application": app_label or ""},
            "confidence": _confidence(total),
            "affected_departments": depts,
            "business_impact": f"{total} interrupted operations across "
                               f"{len(depts)} department(s).",
            "recommended_action": "Teach the recovery once in Knowledge — the lesson "
                                  "propagates to every workflow touching this application.",
        })
    return out


def _learning_transfer(nodes: dict, edges: list) -> list[dict]:
    """Two departments on the same application with a large verified-rate
    gap: one has learned something the other hasn't. Transfer it."""
    by_app: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for e in edges:
        if e["rel"] != "TOUCHES":
            continue
        wf = nodes.get(e["src"], {})
        if wf.get("runs", 0) >= MIN_RUNS_FOR_RATE and "verified_rate" in wf:
            by_app[e["dst"]].append((e["src"], wf))

    out = []
    for app_node, wfs in by_app.items():
        if len(wfs) < 2:
            continue
        best = max(wfs, key=lambda t: t[1]["verified_rate"])
        worst = min(wfs, key=lambda t: t[1]["verified_rate"])
        gap = best[1]["verified_rate"] - worst[1]["verified_rate"]
        if gap < TRANSFER_GAP:
            continue
        d_best = _dept_of(best[0], edges, nodes)
        d_worst = _dept_of(worst[0], edges, nodes)
        app = nodes.get(app_node, {}).get("label", "the application")
        n = best[1]["runs"] + worst[1]["runs"]
        out.append({
            "kind": "learning_transfer", "severity": "medium",
            "headline": f"{d_best} has cracked {app}; {d_worst} hasn't",
            "detail": (f"“{best[1].get('label', '')}” verifies "
                       f"{round(best[1]['verified_rate'] * 100)}% of runs in {app} while "
                       f"“{worst[1].get('label', '')}” verifies "
                       f"{round(worst[1]['verified_rate'] * 100)}%. The gap is learnable: "
                       f"review the stronger operator's record and teach the difference."),
            "evidence": {"application": app,
                         "best": {"workflow": best[0], **{k: best[1][k] for k in ("runs", "verified_rate")}},
                         "worst": {"workflow": worst[0], **{k: worst[1][k] for k in ("runs", "verified_rate")}}},
            "confidence": _confidence(n),
            "affected_departments": sorted({d_best, d_worst}),
            "business_impact": f"A {round(gap * 100)}-point verified-rate gap on a "
                               f"shared application.",
            "recommended_action": "Compare the two records in Evidence and teach the "
                                  "difference as an app-scoped lesson — it propagates "
                                  "immediately.",
        })
    return out


def _redundant_approvals(nodes: dict) -> list[dict]:
    """A capability approved everywhere it appears, across multiple
    workspaces, with zero denials — org-level friction, not caution."""
    out = []
    for n in nodes.values():
        if n["type"] != "capability":
            continue
        approved = int(n.get("approved") or 0)
        denied = int(n.get("denied") or 0)
        workspaces = int(n.get("workspaces") or 0)
        if denied == 0 and workspaces >= 2 and approved >= MIN_CROSS_WS_APPROVALS:
            out.append({
                "kind": "redundant_approvals", "severity": "medium",
                "headline": f"'{n['label']}' approvals are pure friction",
                "detail": (f"Approved {approved} times across {workspaces} workspaces "
                           f"with zero denials. Nobody is exercising judgment here — "
                           f"they are clicking a button."),
                "evidence": {"capability": n["label"], "approved": approved,
                             "denied": denied, "workspaces": workspaces},
                "confidence": _confidence(approved),
                "affected_departments": [],
                "business_impact": f"{approved} human interruptions with no "
                                   f"decision value this period.",
                "recommended_action": "Grant an org-wide standing approval for this "
                                      "capability; keep the audit trail.",
            })
    return out
