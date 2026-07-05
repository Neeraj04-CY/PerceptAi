# Chapter Ω — The PerceptAI Platform

Chapters 1–5 built an exceptional engine. Chapter Ω builds the product
around it: the layer that lets an organization — not a developer with a
terminal — adopt PerceptAI as its AI operating platform.

---

## 1. The audit (what existed before Ω)

The engine was production-grade; the product surface exposed almost none
of it:

| # | Gap | Business impact |
|---|-----|-----------------|
| 1 | **The workforce OS was invisible.** Chapter 5's missions, specialists, evidence graphs, policies and approvals had zero API or UI surface — the product only ran single tasks. | The flagship capability was unsellable. |
| 2 | **The canonical event stream was discarded** after SSE relay. Nothing was replayable: no reasoning traces, no mission timelines, no execution audit. | Observability — the trust foundation — didn't survive the run. |
| 3 | **Single-user product.** No organizations, teams, workspaces, roles, or secrets. | No company could adopt it. |
| 4 | **Every run was a one-off prompt.** No reusable, versioned, parametrized automations; no scheduling. | No compounding value; no operational adoption. |
| 5 | **No approvals surface.** `MissionPolicy` had an approver hook wired to nothing durable. | No human-in-the-loop story for risky capabilities. |
| 6 | **Plan limits hardcoded in three places** (two route files + SQL). | Violated the project's own plans-as-data principle. |
| 7 | **Empty first-run.** A new user landed on a blank dashboard with a prompt box. | Time-to-value measured in confusion. |
| 8 | **No introspection.** `/health` returned `{"status":"healthy"}` regardless of whether the host could execute anything; the plugin registry was invisible. | Operators couldn't answer "can this machine run work right now?" |

Ranking rationale: gaps 1+2 were fixed first because one storage decision
(persist the canonical stream) and one adapter function (mission
streaming) unlock four product pillars at once — Mission Control,
missions, replay, and audit. Org foundations (3) came next because every
other feature needs a scoping model. Workflows (4) ride on both.

## 2. What was built

### Backend (api/)

- **`migrations/002_platform.sql`** — additive schema: `organizations`,
  `organization_members` (RBAC as data), `workspaces` (environments +
  policy JSONB), `secrets`, `workflows` + `workflow_versions`, `missions`,
  `approvals`, `events` (the persisted canonical stream), `audit_log`,
  plus `plans.limits` and scoping columns on `sessions`/`api_keys`.
  `database.sql` stays the 001 baseline; each statement lives in exactly
  one file.
- **`plans.py`** — the single source of plan behavior (DB-first, fallback
  constants). The three duplicated limit dictionaries were deleted.
- **`rbac.py`** — owner/admin/member/viewer with a data permission matrix.
  Pure, fails closed, grants never exceed the actor's own role.
- **`orgs.py`** — org service layer: lazy personal-org bootstrap (existing
  accounts get one on first touch), membership resolution,
  `require_permission`, control-plane audit writer, session scoping.
- **`secrets_crypto.py`** — Fernet vault crypto, key injected (KMS-ready);
  values are write-only through the API.
- **`templates.py`** — the curated gallery: six parametrized templates
  with a validated `{{variable}}` renderer (missing required variables
  are errors, defaults fill the rest).
- **`events_store.py`** — bounded buffer + chunked bulk insert of the
  canonical stream; persistence failure never breaks execution.
- **`executor.py`** — still a thin adapter, now with ONE shared relay
  (`_relay`) powering both `execute_task_stream` (legacy wire v0) and the
  new `execute_mission_stream` (wire v1 = full-fidelity canonical events).
  Both capture events for persistence. Mission runs map control-plane
  dicts onto the engine's typed `WorkspaceContext`/`WorkforceLimits`, and
  plan limits bound the mission loop itself.
- **`sse.py`** — one place that pumps a blocking generator into an async
  SSE response with keepalives (main.py rewritten onto it).
- **Routes** — `org_routes` (orgs/members/workspaces/secrets/audit/usage),
  `mission_routes` (SSE run + history + replay), `workflow_routes`
  (CRUD/publish/render), `approval_routes`, `platform_routes`
  (templates/capabilities/health/session replay). 49 routes total.
- **`scheduler.py`** — schedules are data on the workflow row; an opt-in
  loop (`ENABLE_SCHEDULER`, default off because execution controls the
  host desktop) claims due workflows and runs them through the same
  executor. Task-mode only; mission workflows stay on-demand.
- **Approvals** — grant-ahead model wired into `MissionPolicy`'s existing
  approver hook: an APPROVED row for (workspace, capability) is consumed
  by the next dispatch; otherwise a PENDING row is created and the order
  is denied honestly (`CANCELLED`, policy named). Nothing runs silently.

### Engine (perceptai/) — deliberately minimal

One addition: `streaming.to_platform_sse` (wire format v1) in the one
sanctioned serialization module. No runtime, planner, or workforce
changes — the platform consumes existing contracts.

### Frontend (frontend/)

New information architecture: **Mission Control · Run · Missions ·
Studio · Sessions · Approvals · Analytics · Organization · API Keys.**

- **Mission Control** (`/dashboard`) — stat strip (running / succeeded /
  failed / needs-approval / specialists), live missions + sessions feeds,
  inline approve/deny, usage & workforce budget meters, specialist roster
  from the live registry, host health strip (api/db/engine/scheduler),
  15s refresh. First-run state: three-step onboarding + template gallery.
- **Run** (`/dashboard/run`) — the existing task runner moved intact,
  plus a task/mission mode switch. Mission mode streams wire-v1 events
  into a live work-order board, executive decision ticker and the final
  grounded report. Dead code from the old page (unused non-streaming
  path) was deleted.
- **Missions** — list with status filters and metrics; detail page renders
  the full replayable record: report with per-evidence confidence bars,
  open evidence conflicts (never hidden), collapsible work orders with
  outputs/errors, executive decision log, and the persisted event
  timeline.
- **Sessions** — detail gains the **reasoning replay card**: confidence /
  progress / uncertainty evolution (inline SVG line chart, palette
  validated for CVD + contrast on the dark surface) plus the decision
  trajectory and uncertainty signals.
- **Agent Studio** — workflow library + template gallery; editor with
  instruction + `{{variable}}` slots (undeclared-slot detection with
  one-click declare), variables table, task/mission execution mode,
  draft→publish versioning, schedule presets, and run-with-variables that
  renders server-side and hands off to the Run page — the same execution
  path as any run.
- **Organization** — overview (plan/usage/limits), members with role
  management, workspaces with per-workspace approval-capability toggles,
  write-only secrets vault, audit trail.
- **Approvals** — the full queue with status tabs and decisions.

### Validation

- `pytest tests/ -q`: **296 passed** (267 pre-existing + 29 new platform
  tests: RBAC matrix monotonicity, plans fallback/degradation, secret
  crypto roundtrip + tamper cases, template gallery shape + renderer,
  event buffer capping/chunking, wire-v1 fidelity for every event type).
- `npm run build`: 15 routes compile; `npm run lint`: one pre-existing
  warning (live screenshot `<img>`), zero errors.
- API app imports headless with all 49 routes registered.
- Chart palette: `validate_palette.js` — all checks pass
  (`#3987e5/#199e70/#c98500` on the dark surface).

## 3. Architectural decisions

1. **Persist the canonical stream, derive everything.** One `events`
   table stores `TaskEvent.to_dict()` rows. Replay, mission timelines,
   reasoning traces and execution audit are all *queries*, not systems.
   The engine's "one event stream" invariant now extends to storage.
2. **A workflow is a parametrized mission, not a program.** Agent Studio
   authors text + variables + policy + schedule. Branching and
   parallelism live where they already exist — the engine's WorkGraph —
   so there is no second workflow interpreter and no duplicate execution
   path. Publishing snapshots immutable versions; rendering happens
   server-side and the client executes through the same streaming
   endpoints as any run.
3. **RBAC, plans and policy are rows, not branches.** The permission
   matrix, plan limits and workspace policies are data consumed by one
   checker each. Upgrading a plan changes numbers, never code paths.
4. **Approvals are grant-ahead, not pause-resume.** Suspending a running
   mission mid-flight would require checkpointing the executive loop — a
   large runtime change with real failure modes. Instead approvals are
   durable records consumed at dispatch: deny-by-default, approve
   authorizes the next run. Honest, auditable, and it needed zero engine
   changes. Mid-mission pause is a roadmap item, listed openly.
5. **The API stays a control plane; execution stays host-bound.**
   `executor.py` remains the only engine adapter; mission streaming reuses
   one relay. Wire v1 is defined in `perceptai/streaming.py` — the single
   module that knows wire schemas — so future runner protocols add
   serializers there, nowhere else.
6. **Graceful degradation over hard requirements.** Every platform
   feature 503s with a named hint if migration 002 is missing, while the
   pre-Ω surface (auth, keys, execute, sessions) keeps working untouched.
   Cloud hosts without desktop deps report `engine: false` in health and
   refuse work honestly.

## 4. Tradeoffs made

- **Primary-org UX.** The schema and API are fully multi-org (`org_id`
  everywhere, membership roles), but the dashboard binds to the user's
  first org. An org switcher is UI work, deliberately deferred.
- **Approvals wait for the next run** rather than suspending in-flight
  work (see decision 4). The denied order is CANCELLED with the policy
  named; the operator approves and re-runs.
- **Scheduler executes on the API host.** Right architecture is the
  remote runner; shipping a guarded in-process loop (default off) gives
  scheduling real value today without pretending the runner exists.
- **Secrets are stored, not yet injected.** Piping secret values through
  an LLM-planned instruction would leak them to the model. The vault
  ships (encryption, RBAC, audit, write-only); runtime injection needs a
  typed `type_secret` action in the engine — roadmap, stated in the UI.
- **Event capture is bounded** (2 000 events/run) — long runs truncate
  stored history rather than exhausting memory; live streams are never
  truncated.
- **Session events for tasks are persisted but the session UI reads the
  richer `result.metadata.reasoning`** record for replay; the events
  endpoint exists for deeper tooling.

## 5. Capabilities intentionally rejected

- **Drag-and-drop workflow canvas** — a node graph would demand a second
  execution semantics and turn plain-English instructions into a no-code
  toy. The engine already plans from the live screen; authoring stays
  text-first. (Quality bar: Linear ships text + structure, not canvases.)
- **Marketplace implementation** — the plugin *surfaces* exist
  (`perceptai.specialists` entry points, `/platform/capabilities`);
  a storefront before there are third-party specialists is theater.
- **Remote runner implementation** — the interfaces are already
  runner-shaped (control plane ↔ SSE ↔ typed results); building the
  agent daemon now would duplicate the executor before one customer needs
  fleet execution.
- **SSO/SAML/OIDC** — enterprise auth belongs behind a real identity
  provider integration, not a half-measure; bcrypt+JWT stays until then.
- **Stripe billing** — plans are data and usage is metered; charging is
  configuration, not architecture.
- **Plugin sandboxing** — entry-point specialists run in-process today;
  isolating them properly is the runner's job (per-runner processes).
- **RLS-based multi-tenancy rewrite** — the API is the service-role
  gatekeeper; rewriting auth onto Supabase RLS is a migration with no
  user-visible payoff at this stage.

## 6. Brutally honest product review

**What's now true:** a company can sign up, get an org and workspace,
invite teammates with real roles, gate risky capabilities behind
approvals, author and version parametrized automations, run missions that
fan out across specialists, watch every executive decision live, and read
back a grounded report with per-claim confidence and visible conflicts.
Every admin action is audited; every run is replayable. That is a
product, not a demo.

**What's still weak:**

- **The engine's ceiling is the product's ceiling.** OCR + a 70B planner
  on consumer hardware will fumble dense enterprise UIs. No amount of
  Mission Control polish changes a failed mission report.
- **Execution is wherever the API runs.** The "cloud dashboard, local
  hands" split is real but confusing until the runner exists — a user on
  Railway sees a beautiful console over an engine that reports
  `engine: false`.
- **Approvals interrupt rather than pause.** Operationally fine, but a
  Fortune-500 reviewer will call it out immediately.
- **No e2e tests for the dashboard.** Unit + build + lint is not a UI
  regression net. (The API layer likewise trusts integration behavior to
  typed contracts, not an HTTP test suite.)
- **Analytics is still session-level.** Mission-level economics (cost per
  outcome, specialist ROI) exist in the data and deserve their own view.

## 7. What still blocks Fortune-500 trust

1. **Identity**: SSO (SAML/OIDC), SCIM provisioning, session policies.
2. **Isolation**: dedicated runners with per-workspace credentials;
   plugin process isolation; no shared-desktop tenancy.
3. **Compliance**: SOC 2 controls, immutable audit export, data
   residency, retention policies on events/screenshots (screenshots of a
   finance desktop are sensitive data — today they live in `%TEMP%`).
4. **Reliability**: SLAs need queueing, retries across runner failures,
   and horizontal control-plane deployment — currently one process.
5. **Safety cases**: signed mission policies, dry-run mode, and
   kill-switch semantics stronger than PyAutoGUI's corner failsafe.
6. **Procurement basics**: pen-test report, DPA, uptime history, support
   tiers. Boring, decisive.

## 8. Twelve-month roadmap (ranked by customer value)

| Q | Theme | Deliverables |
|---|-------|--------------|
| Q1 | **Remote runners** | Runner daemon (registers via API key, leases work over the existing SSE/typed contracts), runner fleet page in Mission Control, scheduled workflows execute on runners — kills the "API host = execution host" confusion, unlocks cloud dashboards. |
| Q1 | **Mission economics** | Cost/outcome analytics from mission metrics already persisted; budgets that alert and hard-stop per workspace. |
| Q2 | **Human-in-the-loop v2** | Mid-mission pause on approval (executive checkpointing), NEED_USER surfacing in the dashboard with respond-and-resume, dry-run previews of the work graph before dispatch. |
| Q2 | **Secrets injection** | Typed `type_secret` engine action (value never enters LLM context), vault → runner delivery, rotation audit. |
| Q3 | **Enterprise identity** | SSO/OIDC, SCIM, org switcher UX, invite-by-email flows. |
| Q3 | **Evidence workspace** | Cross-mission knowledge: search the evidence graph, conflict resolution UI, export to sheets/BI — turns runs into a compounding data asset. |
| Q4 | **Plugin ecosystem** | Specialist SDK docs + scaffold, verified plugin registry, per-plugin permissions; marketplace only when ≥ a handful of real third-party specialists exist. |
| Q4 | **Compliance package** | SOC 2 groundwork, retention policies, audit export, screenshot lifecycle management. |

---

*Validation record: 296/296 pytest · Next.js build 15/15 routes · lint 1
pre-existing warning · API 49 routes importing headless. Baselines
unchanged: `reasoning_chapter4-validation.json`,
`workforce_chapter5-validation.json` (no engine behavior touched).*
