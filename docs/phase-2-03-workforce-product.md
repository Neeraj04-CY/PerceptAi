# Phase Two, Sprint 3 — The Workforce Product

*Stop building an agent. Start building a workforce.*

## The test every screen must pass

**"If a COO opened this page, would they immediately understand why this saves their
company money?"** Screens that exist because they were easy to build, or because they
expose internal architecture, are deleted or demoted. The product is the operating
system for running an autonomous operations team — not a console for launching agent
tasks.

## The honesty constraint (non-negotiable)

The directive's Morning Brief example shows "842 invoices processed." We do NOT ship
invented numbers — the product constitution forbids fake KPIs, and so does the
directive itself ("No fake KPIs"). Everything the new surfaces show is **computed from
real rows**: sessions, missions, approvals, attention items, workflow assurance,
fleet autonomy, analytics. Where history is empty, the product says so plainly and
shows the path to the first hire. "Time saved" appears only as a labeled estimate
derived from a template's declared manual-equivalent — never as a fabricated total.

What makes this possible: the platform already measures what competitors fake.
Verified success rates per workflow, evidence-backed autonomy verdicts
(`ready | supervised | in_the_loop | insufficient`), calibration error, per-action
grounding confidence and observed effects (Sprints 1–2), failure taxonomy,
attention queue. The redesign is a truth-telling presentation of measured data.

## Terminology map

| Kill | Replace with |
|---|---|
| Mission Control | **Today** (the Morning Brief) |
| Run / Execute / Task | **Assign work** / **Operations** |
| Sessions | **Operations** (history = the work record) |
| Studio / workflow gallery | **Business Templates** ("hire for a role") |
| Runners | **Machines** — inside Settings, out of the nav |
| Analytics | **Answers** (questions answered, charts demoted to detail) |
| Organization / API Keys pages | **Settings** (one place) |
| "Open Notepad" starter, demo placeholders | **Deleted everywhere.** First run = a business template on your own application. |

Engine-internal vocabulary (runtime, world model, healer) never appears in the UI.

## The new information architecture

Eight surfaces. Each answers exactly one question.

1. **Today** `/dashboard` — *"What did my workforce do, and what needs me?"*
   Morning Brief: greeting, the measured record of the recent period (verified
   operations, flagged items, approvals closed, autonomy earned), what needs a human
   (attention + pending approvals), what's running now. Zero asking "what do you want
   to do" — the page already knows.
2. **Workforce** `/dashboard/workforce` — *"Who works for me and how good are they?"*
   The hero. AI employees = department operators (Finance, Sales, Procurement, HR/IT,
   Support) derived from template packs and the real workflows/runs under each: health,
   trust (verified rate), autonomy earned, recent operations, applications touched.
3. **Operations** `/dashboard/operations` — *"What work was done, and can I trust it?"*
   Unified history (tasks + missions), status in business language, each entry opening
   the story view (goal → what happened → evidence → verification → result).
4. **Templates** `/dashboard/templates` — *"What roles can I hire for?"*
   Department-first catalog. Every template leads with the business goal, systems it
   touches, expected outcome, evidence produced, time given back.
5. **Evidence** `/dashboard/evidence` — *"Can I prove what the workforce did?"*
   The moat. Per-action proof: what was acted on, grounding confidence, sources that
   agreed, the observed change (causal effect attribution), verification checks,
   screenshots, approvals. Impossible to fake because it is the canonical event stream.
6. **Approvals** `/dashboard/approvals` — *"What is asking for my judgment?"*
   Review-request feel: approve / reject with reason, full context inline.
7. **Answers** `/dashboard/answers` — *"Is this working, and where is it going?"*
   Plain-language answers computed from measured data: what succeeded, what failed and
   why, what's improving, which workflows have earned full autonomy, where humans are
   still required. Charts live behind it as supporting detail, not as the product.
8. **Settings** `/dashboard/settings` — workspace, people, secrets, policies, machines
   (runners), developer API, audit. One place, not five nav items.

**Leaves the nav:** Run (becomes the "Assign work" action reached from Today /
Workforce / Templates — the live cockpit remains as the delegation + supervision
view), Runners, Organization, API Keys, Analytics, Missions, Sessions.

## Kill list (effective immediately)

- The Notepad starter task and starter template pack — deleted, frontend and backend.
  First-run now routes to Business Templates ("hire your first employee"), where the
  data-entry template runs against the customer's own application.
- Demo placeholder instructions (search/open-app examples) in the assign-work input.
- "Mission Control" operations-console framing on the home page.
- Nav items that expose architecture (Runners) or developer plumbing (API Keys) at
  top level.

## Visual language

Calm, typography-led, breathing room. One page answers one question — no wall of
tiles. Fewer borders, fewer badges, no decorative KPIs. The existing dark aesthetic
stays; density drops.

## Milestones (each validated, then shipped)

- **A — The workforce IA.** New nav (Today / Operations / Templates / Approvals /
  Answers / Settings), Morning Brief home on real data with an honest first-run
  state, Answers v1, Settings hub, old routes redirect, demo-speak purged
  (frontend + backend catalog). Product builds, driver screenshots verify.
- **B — The hero and the moat.** Workforce page (AI employees over real per-pack
  workflow data), Evidence page (per-action proof chain from the persisted event
  stream), mission/operation detail reframed as a story. Adds Workforce + Evidence
  to the nav when they exist — no dead links, ever.
- **C — Depth.** PR-style approvals, template detail framing (goal / systems /
  outcome / evidence / autonomy), settings sections built out (policies, models,
  notifications), assign-work flow reading fully as "brief an employee".

Docs: this file. Measured validation: `npm run build`, driver `smoke` + screenshots
reviewed by eye, `pytest` for the backend catalog change.
