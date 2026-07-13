# Phase Two, Sprint 6 — Business Memory

*The moat: a workforce that provably knows this company better every week.*

## The investor question this answers

"What becomes impossible for competitors to copy?" Not screens — the **compounding
record of how one specific company operates**: every correction a manager taught,
every approval lesson, every recovery the engine earned against a real application.
After six months, replacing PerceptAI means abandoning the organization's operational
memory. That is the sentence one CIO tells another.

## What was built (the full loop — memory that never reached planning would be a notes app)

**Write** (`api/memory_service.py`, `006_business_memory.sql`):
- **Human teaching**: the Knowledge page's Teach box and the approval decision flow
  (`lesson` on decide; a denial-with-reason auto-becomes a correction). Taught lessons
  start authoritative (0.9).
- **Observed learning**: after every run, successful recoveries on the canonical event
  stream become lessons ("In SAP, a modal dialog can block progress; recovery that
  worked: dismissed with ESC"), scoped to the application.
- **Reinforcement, not duplication**: lessons dedupe on normalized content; repetition
  raises confidence noisy-OR (capped 0.99) and appends bounded evidence refs. The
  organization gets more certain, never noisier.

**Recall** (`api/org_memory.py`): `OrgMemoryStore` decorates the engine's local
MemoryStore at the composition root. The engine calls `recall_knowledge(...)` exactly
as before and receives org lessons merged ahead of local cache — flowing into
`context.facts` → the planner's "Known facts". **Zero engine changes; transport
independence intact.** Recall is deterministic term-matching — no LLM in the loop, and
a dead memory DB never blocks a run.

**Propagation**: lessons scope to `app:<name>` / `workflow:<id>` / `org`. Finance's
SAP lesson reaches Procurement's next SAP run immediately; org policies apply
everywhere. Pinned by test.

**Autonomous optimization** (`approval_insights`): computed live from measured
approval history — a capability approved N consecutive times with zero denials
surfaces as a standing-approval recommendation. Never stored guesses.

**Surface**: Knowledge leads with Business Memory — taught vs observed lessons with
reinforcement counts and scopes, insights, and the Teach input. Managers teach; they
never edit prompts.

## Validation

- 648 tests green (+11 pinning: dedupe/reinforcement, authoritative teaching, recall
  shape = the engine's knowledge-row contract, cross-workflow propagation, org-scope
  vs noise, event-stream learning, streak insights with denial-breaks, decorator
  merge order and DB-failure survival).
- Production build clean; Knowledge screenshot-verified (teach box + honest empty
  state; no fake data).
- Live probe: `GET /memory` returns the honest 503 with the named hint until
  **`api/migrations/006_business_memory.sql` is applied in the Supabase SQL editor**
  (same activation contract as every platform migration). Everything else degrades
  gracefully until then.

## Honest limitations (next in line)

- Remote runner runs don't yet recall org memory (lessons must ride the signed work
  order); local API-host runs get the full loop today.
- Observed learning currently ingests recoveries; injection detections, verification
  contradictions and correction-from-replay are natural extensions.
- Recall is term-match; embedding-based recall is a quality upgrade once volume
  justifies it.
- Mission (workforce) runs share the engine seam but the executor doesn't inject org
  memory there yet.
