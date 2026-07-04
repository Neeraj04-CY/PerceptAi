# Chapter 4 — The Adaptive Reasoning Engine

> Chapter 3 gave PerceptAI eyes. Chapter 4 gives it a thought process:
> every execution is now an evolving cycle of belief, doubt, hypothesis
> and decision — observable, replayable, and measured.

## 1. Audit (after Chapters 1–3)

What existed: one execution loop, goal intelligence, a fused world model
with honest confidence, typed contracts, one canonical event stream.
What was missing was *reasoning about* all of that:

1. **Decisions were hardcoded control flow.** `if not result.ok: heal →
   replan → break` — invisible, unexplainable, untestable in isolation.
2. **Nothing acted on uncertainty.** Confidence flowed through perception
   and stopped. Two `Submit…` buttons, a failed provider, a world that
   didn't change after a click — none of it changed behavior.
3. **No memory of what the agent believes.** `TaskContext.facts` was flat
   strings; nothing tracked "invoice downloaded, 73%" or lowered it when
   the world disagreed.
4. **One explanation per failure.** The healer's first diagnosis was the
   only one; alternatives died unexamined; recovery success was *assumed*
   (recovery steps ran) rather than *measured* (failure actually gone).
5. **Progress = step counts.** "Queue empty + budgets left" stood in for
   "is the business outcome closer?".
6. **Budgets were scattered counters** with no unified view, no pressure
   signal, no adaptive spending.

Two latent defects were found and fixed while building on this audit:

- **Unit tests observed the real desktop.** With `uiautomation` installed,
  the UIA provider ran inside the "hermetic" fake harness (read-only but
  nondeterministic — real focus changes leaked into test worlds). The
  simulation config now disables UIA.
- **Healed-without-doing.** The old healer could mark a failed `type` step
  HEALED after merely refocusing a window — the text was never typed.
  Exposed by the new benchmark's `recoverable_focus_loss` scenario; fixed
  by measured recovery + original-step retry (§5).

## 2. Architecture — and the assumption we rejected

The naive reading of "adaptive reasoning" is an LLM call per cycle:
ask the model what to believe, how sure it is, what to do next. We
rejected it. **The reasoning layer is deterministic computation over
signals the pipeline already produces** — world confidence, WorldDiff,
provider reports, step outcomes, evidence. LLM calls stay exactly where
they were (plan, diagnose, judge). Consequences:

- **Latency stays flat** (reasoning adds microseconds per cycle, not
  seconds) — "latency is a feature" survives the chapter.
- **Every decision is replayable and unit-testable** — 95 new tests run
  in milliseconds; an LLM-judged decision loop could never be pinned.
- **Reasoning is consistent** — the benchmark's determinism probe runs
  every scenario twice and requires identical decision sequences (1.0).
- **Fleet analytics become possible** — deterministic reasoning records
  aggregate; sampled prose does not.

```
                       ┌──────────────── ReasoningEngine (stateless) ───────────────┐
 ExecutionEngine ──────│ BeliefState · UncertaintyTracker · HypothesisGenerator      │
 (the ONE loop,        │ ProgressEstimator · StrategyManager · DecisionEngine        │
  executes Decisions)  │ ExecutionBudgetManager · ConstraintManager · RecoveryManager│
                       └───────────── per-run state: ReasoningState ────────────────┘
```

The runtime loop became:

```
goal → strategy → observe → plan
  ↓ every cycle
decide( beliefs, uncertainty, progress, budgets ) →
  CONTINUE | OBSERVE | ESCALATE_PERCEPTION | VERIFY | REPLAN |
  RECOVER | FINISH | ABORT | NEED_USER
```

The `ExecutionEngine` is still the only loop in the repository; it now
*executes typed Decisions instead of embedding them*. `ReasoningEngine`
is a session-owned, constructor-injectable service; all per-run state
lives in `ReasoningState` (no module-level state anywhere).

## 3. New modules (one responsibility each)

| Module | Responsibility |
|---|---|
| `beliefs.py` | `BeliefState`: beliefs evolve, never overwrite. Support compounds noisy-OR (cap 0.99 — consistent with fusion); contradiction erodes multiplicatively (floored — absence of evidence ≠ proof); every change is a `BeliefUpdate` with cause. `reconcile_with_world` corroborates/contradicts window beliefs against live observations. |
| `uncertainty.py` | `UncertaintyTracker`: typed `UncertaintySignal`s — low world confidence, provider failed/slow, ambiguous labels (similarity or shared leading word), no change after action, empty screen, contradicted beliefs. Noisy-OR overall score. |
| `hypothesis.py` | `HypothesisGenerator`: multiple explanations per failure from signals (modal appeared, focus moved, sparse screen = loading, launcher error, near-match = renamed, wrong app focused) merged with the healer's ranked LLM diagnoses — agreement compounds probability instead of duplicating. Only generic-safe recoveries are auto-grounded (refocus, wait); never app-specific, never blind. |
| `progress.py` | `ProgressEstimator`: business progress from objective/criteria support by beliefs + evidence (+ the planner's "goal achieved" signal). Step counts affect only remaining-time estimates. Risk = noisy-OR(budget pressure, uncertainty, recent failure, stall). |
| `strategy.py` | `StrategyManager`: reusable postures (research, extraction, navigation, workflow, verification, recovery) tuning observation cadence, verification interval, escalation appetite and planner guidance. Deterministic selection from GoalSpec; `register()` = custom-strategy extension point. |
| `decision.py` | `DecisionEngine`: pure function, ordered rules — safety/budgets > failure handling > goal-achieved > staleness > uncertainty > verification cadence > continue. Higher uncertainty automatically shortens the verification interval and can trigger observation/escalation. Every `Decision` carries its factors. |
| `budgets.py` | `ExecutionBudgetManager`: ONE ledger — steps, replans, recoveries, LLM calls, vision escalations, wall-clock. Pressure = tightest budget. Affordability checks are the only budget API the decision engine uses. |
| `constraints.py` | `ConstraintManager`: policy predicates checked before every step; denials are first-class failures that get **replanned around, never healed**. Broken policies fail closed for input actions, open for passive ones. `blocked_window_titles` ships as the config-level example; `register()` = enterprise policy extension point. |
| `recovery.py` | `RecoveryManager`: understand → hypothesize → choose → act → **measure**. A recovery counts only if the original failure condition demonstrably cleared; rejected explanations are never chosen again. |
| `reasoning.py` | `ReasoningEngine` + `ReasoningState`: orchestrates all of the above, owns event emission thresholds, produces the replayable `metadata.reasoning` summary. |
| `simulation.py` | The deterministic fake substrate shared by unit tests and the reasoning benchmark (previously trapped inside `tests/conftest.py`). |

## 4. Runtime changes

- One typed `Decision` per cycle drives the loop (`max_cycles` bounds it
  absolutely). The runtime executes decisions; it never overrides them.
- **Measured recovery with original-step retry.** After recovery actions
  succeed, the original failure condition is re-checked against the fresh
  world (missing element must now resolve; missing window must now
  exist). If cleared, the original step is retried — unless the recovery
  plan already redid it (same action + same primary param), because
  retrying a click can double-submit. "Recovery = wait succeeded" is dead.
- **Replans supersede failures.** A step that failed and was replanned
  around is marked `SKIPPED` (error preserved); verification owns the
  verdict for the new path. Previously any failed step doomed the status
  even when the detour achieved the goal.
- Strategy guidance is injected into the one planner prompt (no second
  planner); recalled memory enters as low-confidence beliefs that only
  live observation can strengthen.
- `VERIFY` cycles reconcile beliefs against a fresh snapshot mid-run
  (observe-only); `ESCALATE_PERCEPTION` spends the vision budget only on
  perception-shaped uncertainty.
- Honest termination: budget exhaustion, planner exhaustion, constraint
  blocks and time-outs all end as explicit FINISH/ABORT/NEED_USER
  decisions on the stream — no silent breaks.

## 5. Event model

Nine additive canonical events: `STRATEGY_SELECTED`, `DECISION_MADE`
(with factors, budget snapshot and a `changed` flag — every decision is
on the record, which replay needs; a bare `DECISION_CHANGED` would lose
the confirmations), `BELIEF_UPDATED` (delta + cause + source),
`UNCERTAINTY_CHANGED` (score + typed signals), `PROGRESS_UPDATED`,
`HYPOTHESIS_CREATED`, `HYPOTHESIS_RESOLVED` (confirmed *and* rejected —
both resolutions are evidence), `RECOVERY_STARTED` (all candidate
hypotheses + the chosen one), `RECOVERY_COMPLETED` (measured outcome).

On the wire they share one additive SSE type `reasoning` (inner `kind`
discriminates); old dashboards ignore unknown types, so the change is
backward compatible, and `api/executor.py` needed zero changes.
`TaskResult.metadata.reasoning` carries the replayable record: strategy,
decision histogram + changes, per-cycle trajectory (decision, reason,
uncertainty, progress), confidence history, top beliefs, hypothesis
stats, final progress and uncertainty signals. A developer can answer
"why did the agent choose this / ignore that / change its mind?" from
the stream alone.

## 6. Frontend

New live **Reasoning panel** on the Run page (between the execution
timeline and the world model), driven purely by the `reasoning` SSE
stream:

- **Goal progress**: single-hue progress ring (business completion, not
  steps), objectives met, risk, estimate trust, "next:" remaining work.
- **Execution budget**: thin meters for steps / replans / recoveries /
  LLM calls / time.
- **Decision feed**: one row per cycle — cycle number, decision chip
  (highlighted border when the decision *changed*), and the reason,
  verbatim from the engine. Plus an uncertainty-per-cycle strip.
- **Beliefs**: confidence meters + statements + signed deltas (cause on
  hover).
- **Hypothesis cards**: kind, probability, explanation, and status as
  icon + label (open / confirmed / rejected) — never color alone.

Encoding follows the world-model panel's system: magnitudes are one-hue
meters, statuses are icon+label, text wears ink tokens, and every
animation reports a state change (feed entries, meter fills, ring
progress) — nothing decorative. `lib/api.ts` gains the typed
`ApiReasoningSummary`. Also: `frontend/.eslintrc.json` now exists —
`npm run lint` used to hang on an interactive prompt.

## 7. Tests

95 new tests (309 assertions run; **204 total, all green**): belief
evolution/contradiction/reconciliation, every uncertainty signal,
deterministic + merged hypotheses, progress (including "five successful
steps, zero business progress"), all decision-rule precedences, budget
pressure/affordability, constraint fail-closed semantics, measured
recovery incl. false-recovery rejection, and runtime integration:
decision events on every cycle, explicit terminal decisions, false
recovery → honest FAILED, confirmed recovery with retried input, replan
supersedes failure, policy denial → replan (never heal), changing-UI
recovery, replayable summary, SSE mapping, cycle budget.

## 8. Benchmarks

`evals/reasoning_bench.py` — **fully simulated, safe anywhere** (real
runtime + `perceptai.simulation`; no screen, no LLM). Ten scenarios:
plain navigation, ambiguous labels, delayed application, changing UI,
incorrect OCR, unrecoverable missing element, recoverable focus loss,
false action success, policy-blocked input, goal-completion loop.

Chapter-4 baseline (`evals/reports/reasoning_chapter4-validation.json`):

| Metric | Value | Reading |
|---|---|---|
| scenario_pass_rate | **1.0** | incl. honest failures behaving correctly |
| task_success_rate | 1.0 | of achievable scenarios |
| false_recovery_rate | **0.0** | the metric this chapter exists to hold at zero |
| recovery_success_rate | 1.0 | recoverable failures recovered *and completed* |
| reasoning_consistency | **1.0** | identical scenario → identical decisions |
| self_report_honesty | 0.7 | underclaiming: 3 successful clicks report UNVERIFIED |
| avg_confidence_error | 0.363 | calibration baseline to drive down |
| avg_decision_stability | 0.417 | short runs change decisions often — relative metric |
| avg_observation_efficiency | 3.63 snaps/step | baseline to drive down |

The honesty/calibration misses are *underclaims* in a static simulated
world (a click that changes nothing cannot be corroborated) — the bench
exists precisely to make that measurable. `evals/harness.py` (real
desktop) now also records `confidence`, `confidence_error`, strategy,
cycles, decision changes and final uncertainty per task, and
`avg_confidence_error` in summaries/compare. **Run `suite_core` +
`suite_business` on the real desktop before merging** (user-executed —
they control the screen).

## 9. Risks

1. **Deterministic heuristics can be confidently wrong** (e.g. sparse
   screen ≠ always loading). Mitigated: hypotheses are probabilistic,
   measured against outcomes, and rejected kinds are never retried;
   false-recovery rate is a tracked metric.
2. **Progress token-overlap matching is crude.** It only feeds decisions
   and reporting (never verification, which keeps the LLM judge + OS
   checks). Underestimating progress costs continuation replans, not
   correctness.
3. **More snapshots on uncertain runs** cost OCR seconds. Bounded by
   consecutive-observation caps, budgets and strategy tolerance;
   observation efficiency is now a benchmark metric.
4. **Retry-after-recovery on non-idempotent actions.** Guarded by the
   redid-original check; clicks whose recovery plan already re-clicked
   are not retried.
5. **Event volume grows** (~2–4 extra events/cycle). Thresholded
   emission (uncertainty/progress deltas), capped trajectories, and the
   SSE type is ignored by old clients.
6. **Behavior change:** a failed-then-replanned step no longer forces
   FAILED (it's SKIPPED; verification decides). Deliberate, documented,
   covered by tests — validate on the desktop suites before merging.

## 10. Subscription value (extension points, no gates in code)

- **Builder** — reasoning replay (the `metadata.reasoning` trajectory +
  event stream are already replayable), strategy visualization (the Run
  panel), confidence analytics (confidence history + calibration error).
- **Scale** — adaptive execution tuning (strategy profiles + budget
  ledger are data, tunable per team), workflow optimization (decision
  histograms across runs), shared knowledge (beliefs feed the existing
  knowledge store).
- **Enterprise** — policy-aware reasoning (`ConstraintManager.register`),
  custom strategies (`StrategyManager.register`), org-wide reasoning
  analytics and audit replay (deterministic reasoning records aggregate;
  every decision carries its factors), compliance history (constraint
  verdicts are first-class outcomes on the audit stream).

## 11. Future extensions

Belief persistence across tasks (beliefs → knowledge store with decay);
learned strategy selection (bench data → selection weights); learned
hypothesis priors per app from confirmed/rejected history; calibration
training (drive `avg_confidence_error` down against desktop ground
truth); NEED_USER surfaced as an interactive pause once the control-plane
protocol exists; per-provider observation targeting (OBSERVE that runs
only the cheap providers); CI gate on `reasoning_bench` regressions.

## 12. Definition of done — self-review

- *Five years?* Perception sources and models will change; "beliefs +
  uncertainty + hypotheses + budgeted decisions, measured by outcomes"
  won't. The reasoning layer is provider-blind and LLM-light by design. ✔
- *One loop?* Still exactly one — it executes typed decisions now. ✔
- *No duplicated reasoning/planning/memory?* Healer remains the only LLM
  diagnosis path; one planner (strategy tunes its prompt); beliefs are
  per-run, knowledge stays in MemoryStore. ✔
- *Would a developer understand why?* Every decision ships with reason +
  factors + budget on the canonical stream and in `metadata.reasoning`. ✔
- *Is honesty enforced, not hoped for?* False recovery is structurally
  rejected (measured conditions), underclaiming is measured (calibration
  error), and the bench holds false_recovery_rate at 0.0. ✔
- *Validated?* 204/204 unit tests; 10/10 simulated scenarios,
  deterministic twice-over; frontend builds + lints. Desktop eval suites
  (`suite_core`, `suite_business`) remain user-executed before merge. ✔
