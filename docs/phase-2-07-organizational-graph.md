# Phase Two, Sprint 8 — The Organizational Graph (Milestone D)

*The business as a connected system. Discoveries emerge from measured
relationships, not isolated statistics.*

## What was built

**`api/org_graph.py`** — the graph substrate and the discovery engine. Workflows,
departments (template lineage), applications, capabilities, failure modes and
Business-Memory lessons are nodes; measured history provides weighted edges
(BELONGS_TO, TOUCHES, FAILS_WITH, APPLIES_TO, run stats, approval outcomes). NO LLM
anywhere; identical inputs produce identical outputs (pinned by a determinism test).

**Discoveries** (`GET /intelligence/discoveries`) — each carries the full contract the
directive demands: evidence, sample-size confidence (never 1.0), affected departments,
business impact in measured terms, one recommended action:

| Discovery | The relationship it reads | Example headline |
|---|---|---|
| **Systemic obstacle** | same failure mode across ≥2 workflows touching the same application | "'modal dialog' is systemic in SAP" — one taught lesson fixes it everywhere |
| **Duplicated work** | two workflows with ≥78% identical briefs, across departments | "Two roles are doing the same job" — merge so evidence compounds in one place |
| **Learning transfer** | ≥35-point verified-rate gap between departments on a shared application | "Sales has cracked Salesforce; Support hasn't" — teach the difference |
| **Redundant approvals** | a capability approved across ≥2 workspaces with zero denials | "approvals are pure friction — nobody is exercising judgment" |

`GET /intelligence/graph` exposes the substrate itself (nodes, edges, counts) — the
foundation every future recommendation surface reads instead of recomputing.

**Surface:** Knowledge gains a "Discoveries" block above the workforce self-review —
no new pages, per the directive.

## The database gap, measured and packaged

Probing the live dev DB proved: **002 is fully applied; 003→006 are entirely
missing** (runners, execution_control, attention_items, learning_consent,
business_memory, and the sessions operations columns incl. `workflow_id`). All their
session ALTERs are `IF NOT EXISTS`-guarded, so the files run as-is:

1. Paste **003 → 004 → 005 → 006** (in order) into the Supabase SQL editor.
2. Verify with the new checked-in tool: `cd api && ..\.venv311\Scripts\python migrations\verify_schema.py`
   → prints PASS/MISSING per migration and an overall verdict.

Until then every dependent surface degrades honestly (probed live: graph/discoveries/
memory/intelligence all return clean 200/503s naming the fix, never a 500).

## Validation

- 664 tests green (+8: graph construction, each discovery's positive AND negative
  threshold case, the full contract on every discovery, determinism, honest
  degradation).
- Production build clean; endpoints probed live.
- No fake data: with an unmigrated DB, discoveries are empty with a named reason.

## Next

- Growing-risk trends (failure counts period-over-period per application).
- Operator merge/specialize suggestions from department×application coverage.
- The graph as recall context: lessons ranked by graph distance, not just term match.
