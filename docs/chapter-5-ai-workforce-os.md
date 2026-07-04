# Chapter 5 — The AI Workforce Operating System

> Chapters 1–4 built one intelligent runtime: perception, planning,
> action, adaptive reasoning. Chapter 5 organizes it. One mission fans
> out into a dependency graph of typed work orders, scheduled across
> specialist execution units that share one world model, one evidence
> graph and one memory — and converge on one business deliverable.

## 1. Audit (after Chapters 1–4)

What existed: exactly one execution loop (`runtime.py`), a session-scoped
composition root (`session.py`), typed contracts for everything that
crosses a boundary, a deterministic reasoning layer, a canonical event
stream, SQLite knowledge memory, evidence-grounded reporting. What was
missing was *organization*:

1. **One task, one session, one thread.** `AgentSession.run()` is
   synchronous and singular. "Research Stripe" runs as one long task
   instead of eleven parallel objectives.
2. **No notion of work above a task.** Nothing decomposes a mission into
   objectives, tracks dependencies between them, or merges their results.
3. **Evidence is a flat list.** `TaskContext.evidence` and the knowledge
   table are append-only rows; corroboration across tasks, conflicting
   values, versions and relationships are invisible.
4. **No routing.** There is nothing to route *to* — capability, cost,
   latency, health and workload are not modeled anywhere.
5. **No organizational memory.** Task patterns exist, but nothing records
   how well an execution unit performs a kind of work, so nothing gets
   structurally faster or cheaper with use.
6. **No tenancy or policy above steps.** `ConstraintManager` gates
   individual steps; organizations, projects, plan limits, approvals and
   audit have no architectural home.

## 2. Rejected assumptions

The naive reading of "AI workforce" is a crew of LLM agents chatting with
each other. We rejected it — and four other tempting shortcuts:

- **Rejected: agents that talk to each other.** LLM-to-LLM conversation
  is unbounded in cost, unreplayable, and unverifiable. Here, specialists
  never communicate. They receive a typed `WorkOrder`, return a typed
  `WorkResult`, and all coordination is the Executive folding results
  into shared state (outputs, evidence graph) that seeds downstream
  orders. Coordination is data flow, not dialogue.
- **Rejected: an LLM in the scheduling loop.** The Executive's cycle —
  what is ready, who runs it, what got stuck — is deterministic
  computation over the work graph, exactly as Chapter 4's decision cycle
  is deterministic over runtime signals. LLM calls stay at boundaries:
  goal analysis, mission decomposition, and the existing plan / diagnose /
  judge / compose calls inside the runtime. A mission with N orders costs
  O(N) boundary calls, not O(cycles).
- **Rejected: a runtime per specialist.** A "Browser Agent" that owns its
  own execution loop would duplicate perception, healing and reasoning.
  Runtime-backed specialists are *capability profiles over the one
  runtime* — same `AgentSession.run()`, different strategy posture and
  instruction shaping. Compute specialists (memory recall, evidence
  review) are pure functions over shared state, no runtime at all.
- **Rejected: pretending one desktop is many.** Parallel desktop
  automation on one machine is a lie — two specialists cannot own the
  mouse. Work orders declare *resource* requirements; the `RunnerPool`
  models physical execution surfaces (today: one local desktop with one
  shared session — one world model, no duplicated perception). Compute
  work parallelizes freely; desktop work serializes honestly on the lease.
  A fleet of remote runners is more runners in the pool, not a redesign.
- **Rejected: feature flags for pricing tiers.** Plans are
  `WorkforceLimits` presets — data (parallelism, order caps, capability
  allowlists, approval requirements), not `if plan == "enterprise"`
  branches in the engine.

## 3. Architecture

```
                    ┌────────────── ExecutiveOrchestrator ───────────────┐
 Mission ──────────►│  GoalAnalyzer (reused)  ·  MissionPlanner (LLM ×1) │
                    │  WorkGraph (deps, ready-set, cascade, stall)       │
                    │  MissionScheduler (pure: one MissionDecision/cycle)│
                    │  SpecialistRegistry (capabilities, health, stats)  │
                    │  MissionPolicy (limits, approvals) · budgets ledger│
                    └───────┬──────────────────┬─────────────────┬───────┘
                            │ WorkOrder        │ WorkOrder       │
                    ┌───────▼──────┐   ┌───────▼──────┐   ┌──────▼───────┐
                    │ Runtime      │   │ Runtime      │   │ Compute      │
                    │ specialist   │   │ specialist   │   │ specialist   │
                    │ (profile)    │   │ (profile)    │   │ (pure fn)    │
                    └───────┬──────┘   └───────┬──────┘   └──────┬───────┘
                            │ lease            │ lease           │
                    ┌───────▼──────────────────▼──────┐          │
                    │ RunnerPool: one AgentSession per │          │
                    │ desktop — ONE world model/memory │          │
                    └───────┬──────────────────────────┘          │
                            │ WorkResult (typed)                  │
                    ┌───────▼─────────────────────────────────────▼──────┐
                    │  EvidenceGraph (claims: corroborate/version/conflict)
                    │  outputs store → seeds downstream WorkOrder inputs │
                    │  ExperienceStore (mission + specialist performance)│
                    └───────────────────┬────────────────────────────────┘
                                        ▼
                     ReportBuilder (reused) → one TaskReport deliverable
```

**Execution model.** `Workforce.run_mission(instruction)`: analyze goal
(reused `GoalAnalyzer`) → recall knowledge → decompose into work orders
(one LLM call, deterministically validated: unknown capabilities dropped,
dependency cycles broken, caps enforced; degrade path = one order) →
build `WorkGraph` → then one typed `MissionDecision` per cycle: DISPATCH
(route ready orders to the best specialist and submit), WAIT (for a
completion), REASSIGN (failed order, attempts left, alternate specialist),
CANCEL_DUPLICATE (two pending orders producing the same keys for the same
entities), FINISH, ABORT. Every decision carries its factors and lands on
the canonical event stream. Completions fold `WorkResult.outputs` into
the shared outputs store and `WorkResult.evidence` into the
`EvidenceGraph`; failed orders cascade SKIPPED to dependents that lost
their only producer. Final deliverable: the reused `ReportBuilder`
composes one `TaskReport` from the evidence graph only.

**The Executive never executes.** It plans, routes, dispatches, measures,
merges, and reports. All work happens inside specialists.

**Routing is scored, never hardcoded.** Candidates = registry records
whose profile covers the order's capability and whose health holds.
Score = expected success (measured `ExperienceStore` rate when ≥3 samples,
else profile baseline) − cost pressure − workload fraction, deterministic
name tiebreak. New specialists (plugin `register()` or
`perceptai.specialists` entry points) join routing with zero runtime
changes.

**Evidence becomes a graph.** `EvidenceClaim` = entity → attribute →
value with sources, confidence, timestamps and versions. Same value from
a new source corroborates (noisy-OR, capped 0.99 — same formula as
perception fusion); a different value creates a new version and an open
conflict when both sides are credible. Relations link entities. Reports
are generated from current claims; durable persistence stays in the ONE
knowledge store (`MemoryStore`) — the graph is the mission-scoped truth,
not a second database.

**Knowledge evolution.** Every mission records outcome, duration and cost
per specialist per capability in `ExperienceStore`; routing consumes the
measured rates, so the organization provably reroutes toward what works.

**Enterprise foundation as extension points.** `WorkspaceContext`
(organization / project / user / roles / plan) scopes every mission and
stamps every event. `WorkforceLimits.for_plan()` maps Starter → Builder →
Scale → Enterprise onto data. `MissionPolicy` reuses `ConstraintVerdict`
for order-level denials (denied ≠ failed: denied orders are CANCELLED
with the policy named) and hosts the approval hook (a callable — approval
chains plug in without engine changes). The audit log is a subscriber on
the event stream — events were already the observability spine; audit is
a consumer, not a new system.

## 4. Module map (`perceptai/workforce/`, dependencies flow downward)

- `contracts.py` — every workforce cross-boundary type: `SpecialistProfile`,
  `WorkOrder`, `WorkResult`, `Mission`, `MissionResult`, `MissionDecision`,
  `EvidenceClaim`, `EntityRelation`, `WorkforceConfig`, statuses/enums.
- `evidence_graph.py` — `EvidenceGraph`: ingest/corroborate/version/
  conflict/relate/query; report evidence; persist via `MemoryStore`.
- `policy.py` — `WorkspaceContext`, `WorkforceLimits` (+plan presets),
  `MissionPolicy`, `AuditLog`.
- `graph.py` — `WorkGraph`: data-key + explicit dependencies, ready-set,
  cycle detection, duplicate detection, failure cascade, stall detection.
- `specialist.py` — `Specialist` interface, `MissionContext`,
  `RuntimeSpecialist` (capability profiles over the one runtime),
  compute specialists (memory recall, evidence review), builtin set.
- `registry.py` — `SpecialistRegistry`: records with live workload and
  measured stats, capability lookup, entry-point discovery.
- `experience.py` — `ExperienceStore` (SQLite, same db file as memory):
  mission history + per-specialist per-capability performance.
- `scheduler.py` — `RunnerPool` (resource leases; one session per
  desktop) and `MissionScheduler` (pure decisions + routing scores).
- `executive.py` — `ExecutiveOrchestrator`: the mission loop, thread
  pool, event emission, evidence merge, budget ledger, final report.
- `__init__.py` — `Workforce` facade: config in, `MissionResult` out.

The kernel (`perceptai/*.py`) does not import the workforce layer;
`workforce/` composes kernel services and never reaches around them.
New mission-level events extend the one `EventType` enum; consumers
derive views from the same stream as always.

## 5. Risks identified (and their mitigations)

- **Two threads, one mouse.** A session is not thread-safe and the
  desktop is exclusive. Mitigation: `RunnerPool` leases — one session per
  runner, one runner per desktop, blocking exclusive lease; compute
  specialists never touch a session.
- **LLM decomposition returns garbage.** Mitigation: decomposition output
  passes deterministic validation (capability whitelist from the live
  registry, cycle breaking, order caps) and degrades to a single work
  order — a mission can never be *worse* than Chapter 4's single task.
- **Runaway cost.** Mitigation: the mission budget ledger (orders, cost
  units, wall clock, cycles) is checked every scheduling cycle; ABORT is
  a first-class decision with the exhausted budget named.
- **Deadlock.** Mitigation: `WorkGraph.stalled()` detects
  nothing-ready/nothing-running/pending-remaining; the cascade marks
  orphaned dependents SKIPPED with the causing order named; if the graph
  remains stuck the mission aborts honestly rather than spinning.
- **Dishonest mission status.** Mitigation: `PARTIAL` is a first-class
  terminal status (some objectives completed, some not); the report is
  composed from the evidence graph only, and conflicts stay visible in
  the result rather than being silently resolved.
- **Duplicate perception.** Mitigation: specialists on the same runner
  share that runner's session — one world model, one memory, one OCR
  pass; the evidence graph deduplicates findings across specialists.

## 6. What Chapter 5 deliberately does not do

- No second runtime, planner, healer or reasoning engine — runtime
  specialists call `AgentSession.run()`.
- No API/dashboard mission surface yet — the engine-level mission result
  and event stream are designed for it (SSE adapters consume the same
  bus), and wiring the control plane is the next increment.
- No marketplace, no remote runner protocol — but orders, results and
  the registry are process-agnostic typed data, which is precisely what
  a control plane serializes later.

## 7. Validation (measured)

- **267 unit tests pass** (63 new across `tests/test_work_graph.py`,
  `test_evidence_graph.py`, `test_specialist_registry.py`,
  `test_mission_planner.py`, `test_mission_scheduler.py`,
  `test_workforce_policy.py`, `test_experience.py`, `test_executive.py`)
  — hermetic, on the simulation substrate (`FakeSpecialist`,
  `ScriptedMissionPlanner` in `perceptai/simulation.py`). The Chapter-4
  reasoning bench is unchanged (no regression).
- **`evals/workforce_bench.py`: 8/8 scenarios pass** (fully simulated —
  no screen, no LLM). Baseline
  `evals/reports/workforce_chapter5-validation.json`:

  | metric | value |
  |---|---|
  | mission_success_rate | 1.0 |
  | self_report_honesty | 1.0 |
  | scheduling_consistency (identical mission → identical decisions) | 1.0 |
  | report_grounding | 1.0 |
  | reassignment_recovery | true |
  | duplicate_work_avoided | true |
  | avg_parallel_speedup (4 objectives, one machine) | 2.45× |

  One finding fixed during validation: the ready-set broke priority ties
  on random order ids, making dispatch order nondeterministic across
  identical missions — exposed by the consistency probe, fixed by a
  stable objective tie-break.
