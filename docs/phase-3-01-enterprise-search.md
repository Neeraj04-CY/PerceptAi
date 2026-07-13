# Phase Three, Milestone 1 — Enterprise Search & the Organizational Timeline

*"PerceptAI now understands our company better than any single employee" starts
with being able to ASK the company anything — and getting grounded, linked answers.*

## What was built

**`api/org_record.py`** — two read-models over the SAME tables the platform already
writes. No new storage, no LLM, no synthesis; every result points back at the row it
came from.

- **`GET /search?q=`** — grounded organizational search across six sources: Business
  Memory lessons, workflows, operations, approvals, attention items, and the audit
  trail. Deterministic term ranking (title matches weighted 2×, recency as
  tiebreaker), typed hits with snippets and navigation refs. It answers the
  directive's questions directly:
  - *"What policies affect SAP?"* → the SAP lessons, the SAP workflows, the SAP runs.
  - *"Why does the invoice workflow fail?"* → its failed operations with their
    measured failure types.
  - *"Who approved erp_write?"* → the approval records with decisions and reasons.
- **`GET /timeline?limit=`** — one chronology of the organization: runs, decisions,
  lessons, escalations, administrative actions, merged newest-first. The history of
  the company on one axis, as API.

**⌘K becomes organizational search.** The command palette now debounces the query
against `/search` and appends grounded hits (typed icons, status, snippet) below
navigation — selecting one jumps to the workflow, operation, approval or lesson it
came from. Search is additive and non-blocking: if the API is unreachable the
palette still navigates.

## Flywheel compliance (the Phase-3 rule)

This strengthens existing capabilities rather than standing alone: memory becomes
*findable*, evidence becomes *citable*, intelligence findings become *navigable*,
and the timeline makes the compounding record *visible*. Both capabilities are
APIs first — the UI consumes exactly what an enterprise integration would.

## Honesty contract (pinned by tests)

- Missing tables (unmigrated databases) are skipped and NAMED in
  `sources_skipped` with the `verify_schema.py` pointer — never fabricated,
  never a 500.
- A query with no meaningful terms is answered honestly, not guessed at.
- Ranking is deterministic; every hit carries its relevance and its source ref.

## Validation

- 670 tests green (+6: cross-source grounding, title-over-body ranking,
  approval attribution, named skipped sources, honest empty query, timeline
  ordering and merging).
- Production build clean; endpoints probed live against the dev database
  (workflow hits returned; unmigrated sources named).

## Next in the Phase-3 queue

Organization DNA (the operating profile derived from history), Continuous
Improvement (the Monday self-review — briefing + discoveries + week-over-week
deltas as one artifact), Process Evolution suggestions, and the timeline surfaced
in the product (the API ships first, per the directive).
