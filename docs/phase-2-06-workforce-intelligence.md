# Phase Two, Sprint 7 — Workforce Intelligence

*Business Memory made PerceptAI hard to replace. Workforce Intelligence makes it
hard to compete with: the workforce observes itself, understands itself, and
advises the business.*

## What was built

`api/intelligence.py` — a deterministic analysis layer over the measured record
(sessions, approvals, business memory, attention). **No LLM anywhere in the module;
no invented insights; no fabricated ROI.** One endpoint, `GET /intelligence/briefing`,
computes the workforce's self-review live:

| Finding | Derived only from | Evidence threshold |
|---|---|---|
| **Strength** — "this responsibility is proven" | verified rate over recent runs per workflow | ≥5 runs, ≥90% verified |
| **Struggle** — "this is failing, here's the measured obstacle" | failure/review rate + `failure_type` taxonomy per workflow | ≥3 runs, ≥40% troubled |
| **Automation opportunity** — "the same brief keeps being typed by hand" | near-identical ad-hoc instructions (normalized) without a workflow | ≥3 repeats |
| **Intervention** — "humans are reviewing too much of the work" | unverified share + open attention queue | ≥30% review share / ≥5 open items |
| **Approval friction** — "this approval looks unnecessary" | consecutive-approval streaks (denials break them) | ≥10 consecutive |
| **Policy candidate** — "a learned lesson deserves to become permanent policy" | observed Business-Memory lessons re-reinforced by real runs | ≥3 reinforcements |

Every finding carries its evidence (counts, rates, ids) so any claim is auditable
against the same tables it came from. Findings rank most-actionable first. When the
period holds too little history, `coverage` says so plainly and the list is empty —
insufficiency is a first-class answer.

**Surface:** Knowledge gains "The workforce, observed" — the manager's review of how
the workforce is *evolving*, not just what it finished — directly under Business
Memory, closing the loop: observed lesson → reinforced by runs → nominated as policy
→ one click of teaching makes it authoritative.

## Why this is the second moat

Business Memory compounds *facts about the company*. Workforce Intelligence compounds
*judgment about the workforce*: which operators deserve more autonomy, which approvals
have become theater, which hand-typed briefs are jobs waiting to be hired for. Both are
derived from a private operational record no competitor can synthesize — and both get
better every month the customer stays.

## Validation

- Unit tests over the control-plane fake pin every threshold: strengths need a real
  track record (4 verified runs stay silent), struggles name the measured obstacle,
  two ad-hoc repeats stay quiet while four speak, taught lessons are never
  re-nominated as policy, empty history reports honest insufficiency, ranking is
  severity-ordered.
- Production build clean; briefing section renders only when findings exist.
- The endpoint needs no new schema — it reads tables that already exist, so it works
  the moment the API restarts (Business-Memory-derived findings activate with 006).

## Honest limitations (next)

- Department-level roll-ups (per-operator brief lines on the Workforce page) are
  presentation work on the same endpoint — queued.
- "Hours/money saved" stays out of the briefing until the ROI baseline model lands
  (template-declared manual-equivalents × verified runs, labeled as estimates).
- Ad-hoc repetition matching is normalized-prefix; embedding similarity is a quality
  upgrade at volume.
