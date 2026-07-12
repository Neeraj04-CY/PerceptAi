# Phase Two, Sprint 1 — Calibrated Verification

*The platform should always know what it knows, what it doesn't, and when not to act.*

## The audit

Phase Two opened with a measured audit of the platform instead of a feature request. The
latest reasoning-bench report (`evals/reports/reasoning_chapter16.json`) showed the single
worst trust number on the platform:

| Metric | chapter 16 |
|---|---|
| scenario pass rate | 1.00 |
| **self-report honesty** | **0.75** |
| **avg confidence error** | **0.303** |
| false recovery rate | 0.00 |
| reasoning consistency | 1.00 |

In 3 of 12 scenarios the engine **succeeded and then reported `unverified` at confidence
0.0** — a calibration error of 1.0 on wins. Running the enterprise bench surfaced a second,
worse fact: the flagship credentialed workflow (Salesforce login + secret injection) had
silently regressed to FAIL on HEAD — `SECRET_USED=False` — a security control no longer
holding end-to-end.

## Root causes

**1. Verification was blind to the engine's own measured evidence.** The verifier derived
positive checks only from `open_app` / `focus_window` / `type` / `read_screen` steps. A
task whose effective steps are clicks — submit a form, dismiss a dialog, toggle a setting,
i.e. the most common desktop actions — could *never* produce a passing check. Its only
signal was the advisory first-vs-last world diff; when that was inconclusive, the run
landed `UNVERIFIED` at 0.0 even though the fused world model had grounded the click on the
exact requested target at measured confidence the instant before acting. In production
this means honest successes page humans, and "confidence is honest" was factually false.

**2. Confidence was a flat pass ratio.** `passed / total` treats a measured 0.95 grounding
and a best-effort browser-existence guess as equal votes, reports 1.0 (forbidden
certainty) when everything passes, and 0.0 (forbidden despair) when only advisory checks
fail.

**3. The critic's `missing_context` check matched windows by exact set membership.** The
planner says `salesforce`; the OS window is `Salesforce Login`. Every other window
resolution in the engine is substring-based; the critic's wasn't. Five false MEDIUM flags
sank a valid plan below the reject threshold — which is how the secret-injection workflow
died: plan rejected → replan → nothing executed. It was also the one critic check with
zero test coverage.

**4. Two checks vetoed what they should only discount.** `input_target_exists` failed
critically when the planner's app alias ("erp") didn't match the real window title ("SAP
Invoice Entry") — and typing into a dialog that closes on submit is a *normal success
path*. `extraction_present` critically vetoed action tasks that read nothing en route,
duplicating protection the criteria judge already provides (critically) for information
goals.

## The change

All in `perceptai/verification.py`, `perceptai/critic.py`, `perceptai/contracts.py`.

- **Grounded-action evidence.** Every successful element-targeted action already records
  what it resolved (`element`, fused `confidence`, contributing `sources`) at act time.
  The verifier now turns each into an advisory `action_grounded:` check whose *strength is
  the measured grounding confidence* — weak perception never inflates certainty, and
  grounding corroborates but never overrides a failed critical check.
- **Calibrated confidence.** `VerificationCheck` carries a `strength` (measured where
  possible, fixed source-weight otherwise). Confidence = noisy-OR support over passed
  checks, multiplicatively discounted by failures (critical at full strength, advisory at
  a fraction) — the same corroboration/contradiction shape as fusion and beliefs, capped
  at 0.99. The verdict stays conservative: critical checks gate it, and support below a
  floor (0.5) is never claimed as verified.
- **Critic window matching** is now substring-containment both ways, consistent with the
  rest of the engine. `missing_context` gained its first regression tests (the untested
  check was the one that regressed).
- **`input_target_exists` and `extraction_present` are advisory** — they dent confidence
  visibly, they no longer veto runs whose outcome other evidence confirms. Information
  goals remain protected by the criteria judge, which stays critical for them.

## Measured results

Unit suite: 622 passed (was 620; +6 verification calibration tests, +2 critic regression
tests, 6 obsolete assertions updated for the capped-confidence semantics).

| Metric | chapter 16 | phase 2 | |
|---|---|---|---|
| reasoning: self-report honesty | 0.75 | **1.00** | every run now claims its true outcome |
| reasoning: avg confidence error | 0.303 | **0.188** | wins no longer reported at 0.0 |
| reasoning: pass rate / false recovery / consistency | 1.0 / 0.0 / 1.0 | 1.0 / 0.0 / 1.0 | no regressions |
| workforce bench (8 scenarios) | all pass | all pass | no regressions |
| critic A/B: wrong irreversible actions prevented | 3→0 | 3→0 | safety preserved |
| enterprise bench | 4/5 on HEAD | **5/5** | secret injection control restored |

Honest nuances, stated plainly:

- The three fixed scenarios report ~0.51 confidence, not ~0.9: that is the *measured*
  fused confidence of a single-source OCR grounding, discounted for no visible world
  change. Multi-source corroborated grounding (UIA+DOM+OCR) scores materially higher.
  This is calibration working, not a shortfall.
- The ERP bench workflow still ends `unverified` (at ~0.33 rather than 0.0): that run
  extracted no evidence, its scripted world never visibly changes, and its window alias
  never resolves. An operator *should* see that flagged. The bench accepts it.
- The uncertain-perception payment click in the critic bench stays `unverified` — low
  grounding does not get promoted to completed. The floor holds.

## Roadmap — next highest-leverage work (in order)

1. **Per-step effect attribution.** The runtime snapshots between cycles; attribute each
   world diff to the step that caused it and record it on `StepResult`. Turns the coarse
   first-vs-last `world_changed` check into per-action causal evidence — the strongest
   verification signal available without any new perception cost, and it would confirm
   ERP-style flows honestly.
2. **Reactive simulation.** Scripted screens advance per snapshot, so perturbations
   dissolve under find-retry (the modal-recovery scenario never actually exercises
   recovery; `recovery_success_rate=0.667` is partly a fixture artifact). Make the sim
   substrate react to actions (clicking "OK" dismisses the modal; otherwise it persists).
   This makes recovery measurement honest and unlocks harder scenarios.
3. **Close the learning loop on calibration.** Verification outcomes → memory/experience:
   learned per-app grounding priors replacing fixed strengths; Brier-score calibration
   tracking per workspace in analytics (real runs, not just benches).
4. **Critic coverage discipline.** Every deterministic critic check gets a positive and a
   negative test (started here). A safety layer with untested checks is how this
   regression shipped.
5. **UI v2** — after the engine items: the directive is intelligence over infrastructure.

## Verification integrity note

This sprint *changed the meaning* of `verified` and `confidence`. The change is strictly
evidence-expanding: no check was removed, critical checks still gate the verdict, honest
failures still report 0.0, and everything above is pinned by tests and reproducible via:

```powershell
python -m pytest tests/ -q
python -m evals.reasoning_bench --label phase2-verification
python -m evals.workforce_bench --label phase2-verification
python -m evals.enterprise_bench
python -m evals.critic_bench
```
