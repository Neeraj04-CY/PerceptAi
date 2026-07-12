# Phase Two, Sprint 2 — Causal Verification

*The difference between "we clicked Save" and "we clicked Save and watched the world respond."*

## The bottleneck

Sprint 1 made verification consume the run's own measured evidence, but two structural
gaps remained, identified in its roadmap:

1. **Verification saw correlation, not causation.** The only world-change signal was a
   coarse first-vs-last comparison across the whole run — which credits a click for
   whatever an app did on its own (an app finishing loading "verified" an unrelated
   click), and cannot say *which* action produced *which* change.
2. **The simulation substrate couldn't measure cause and effect at all.** Scripted
   screens advanced per *snapshot*, so perturbations dissolved by observation alone: the
   modal-dialog scenario's alert vanished after four snapshots whether or not recovery
   ran. The engine dodged the modal via find-retries, the metric punished it
   (`recovery_success_rate` 0.667), and no bench could reward an action for actually
   changing the screen.

## The change

**Reactive simulation** (`perceptai/simulation.py`): a `SimulatedDesktop` owns screen
state; perception reads it, actions mutate it. Declared reactions map a clicked element
("OK"), a key press ("key:esc") or typed text ("type:hello") to the next screen; without
a matching action the screen *persists*. The legacy screens-list behavior is unchanged
(fully backward compatible — zero test edits needed). Bench scenarios now behave like
real UIs: buttons navigate, typed text appears, and the modal stays up until ESC actually
dismisses it.

**Per-step effect attribution** (`perceptai/runtime.py`): the runtime attributes each
post-action world diff to the state-changing step that preceded it, recorded as
`StepResult.data["effect"]`. "No change yet" can be upgraded by a later snapshot (slow
renders); an observed change closes the attribution — effects are never back-attributed.
**Secret-injection steps are exempt**: a secret step records the masked reference and
nothing else, never observation-derived data that could echo screen content (the pinned
security test caught exactly this during development).

**Causal checks** (`perceptai/verification.py`): each attributed effect becomes an
advisory `action_effect:` check with asymmetric strength — an observed change right after
an action is strong confirmation (0.75); absence is a mild contradiction (0.55), because
many legitimate actions render nothing. When per-step attribution exists, the coarse
first-vs-last check is superseded: causal evidence replaces correlation.
`STATE_CHANGING_ACTIONS` moved to `contracts.py` — one source of truth shared by runtime
and verifier.

## Measured results

631 unit tests pass (+9: desktop reactivity, runtime attribution, verifier consumption,
secret-step exemption held by the existing pin).

| Metric | ch. 16 | Sprint 1 | Sprint 2 |
|---|---|---|---|
| self-report honesty | 0.75 | 1.00 | **1.00** |
| avg confidence error | 0.303 | 0.188 | **0.048** |
| recovery success rate | 0.667 | 0.667 | **1.00** |
| false recovery rate | 0.0 | 0.0 | 0.0 |
| reasoning consistency | 1.0 | 1.0 | 1.0 |
| observation efficiency | 3.63 | 3.63 | 3.38 |
| workforce bench | all pass | all pass | all pass |
| enterprise bench | 4/5 | 5/5 | **5/5** |
| critic A/B prevention | 3→0 | 3→0 | 3→0 |

Honest readings, stated plainly:

- **Part of the confidence-error gain comes from the fixtures, part from the engine.**
  The old static screens under-informed verification (a click *couldn't* be seen to work);
  the reactive fixtures reflect how real UIs behave, and effect attribution converts that
  behavior into evidence. Both were required; neither alone produces 0.048.
- **The recovery number is now honestly earned.** Before, the scenario let the engine
  bypass recovery and the metric punished it — a fixture artifact either way. Now the
  modal persists until dismissed, recovery *must* fire, and it does: diagnose →
  hypothesis → ESC → condition measurably cleared → original click retried → landed.
- **Workday (enterprise bench) moved `completed` → `unverified`.** Its scripted screens
  never respond to actions, and causal evidence correctly refuses to credit the
  whole-run change to the actions themselves. The chapter-10 baseline was also
  `unverified`; the bench accepts either. On a real desktop, submitting a form produces
  visible feedback and the causal check confirms it.
- On a real desktop the effect signal costs **zero additional perception** — the
  runtime already takes those snapshots; it now attributes them.

## What this buys customers

Verification statements upgrade from "the screen is different than when we started" to
"**this** action produced **this** response" — per action, on the event stream, in the
report. That is the evidentiary standard an auditor, an operator, and a CIO evaluating
autonomy all need, and it is the foundation the learning loop (next sprint) trains on.

## Next bottleneck (roadmap, in leverage order)

1. **Close the learning loop on calibration** — verification outcomes → memory: learned
   per-app grounding/effect priors replacing fixed strengths; per-workspace calibration
   (Brier) in analytics from real runs.
2. **Critic coverage discipline** — every deterministic critic check gets positive and
   negative tests (missing_context landed in Sprint 1; ambiguity/redundancy/unsafe-action
   still have partial coverage).
3. **UI v2** — surface the causal evidence chain in the run cockpit (each action with its
   observed response), then the workforce-identity surfaces.

## Reproduce

```powershell
python -m pytest tests/ -q
python -m evals.reasoning_bench --label phase2-causal
python -m evals.workforce_bench --label phase2-causal
python -m evals.enterprise_bench
python -m evals.critic_bench
```
