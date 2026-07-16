# Reliability Ledger — the only KPI is verified mission success

Feature freeze. Nothing ships that doesn't raise mission completion, recovery, or
lower latency/thrash. Every failure below was root-caused from a **real desktop run**
(autopsied from the persisted event record), fixed generally, and pinned by a test.

## The single decisive finding: the planner is running on the fallback model

The engine is **frontier-first, degrade-safe**: with `ANTHROPIC_API_KEY` set, planning
and reasoning route to Claude Sonnet; without it, everything falls back to Groq
llama-3.3-70b. **This machine has no `ANTHROPIC_API_KEY` configured**, so the single most
demanding cognitive task — planning a desktop UI navigation — has been running on the
fallback model the whole time. That is why repeated runs of the *same* task failed
*differently* each time (premature "done", transient empty plans, filler-only plans):
llama has high planning variance for desktop UIs.

**Highest-leverage reliability action, and it is a config change only the operator can
make:** set `ANTHROPIC_API_KEY` in `api/.env`. Planning then routes to
`claude-sonnet-5`, and the "Maximum reliability" execution mode already forces the
frontier provider. The engine code is ready; the model is not wired.

## Bugs found and fixed this sprint (all general, all tested)

| # | Symptom (real run) | Root cause | Fix | Test |
|---|---|---|---|---|
| 1 | 139s run, 16 straight `recover` decisions | `_recover` early-returned on exhausted budget without marking the attempt → decision engine chose RECOVER on a no-op forever | RECOVER branch consumes the attempt up front | `test_recovery_never_spirals_when_budget_exhausts` |
| 2 | verify-every-step (9 verifies in 12 steps) | verify interval could floor at 1 | floored at every-2-steps | reasoning bench |
| 3 | ~17s burned before first action | vision escalation / observe fired at cycle 1 | require `executed_count > 0` before escalating | reasoning bench |
| 4 | 60s of reload/read/focus filler | planner emitted orientation thrash the runtime makes redundant | `_strip_filler` (focus beside actions, orientation reads) + prompt | `test_planner_strips_focus_and_orientation_filler` |
| 5 | data-entry ended after `open`, never typed | filler-stripping emptied an all-filler plan → empty queue reads as "goal done" | never empty a non-empty plan; keep the most-actionable step | `test_all_filler_plan_never_empties_to_premature_finish` |
| 6 | typed text, but verdict = unverified | criterion judge saw only `read_screen` findings, not the window title showing the typed text | judge now receives window titles + typed text + per-step effects | `test_judge_sees_window_titles_and_typed_text` |
| 7 | run died at 7s: "Could not plan task" | one transient empty/malformed plan call killed the mission | retry the initial plan once on a transient failure | runtime tests |
| 8 | run ended in 5s, zero steps | planner returned `[]` ("goal done") before any action, criteria unmet | reject a premature goal-achieved signal | `test_premature_goal_achieved_is_rejected` |
| — | "play the first song" reported COMPLETED but never played | judged-unmet criterion outvoted by grounded clicks | an unmet completion criterion caps confidence below the verified floor | `test_play_criterion_unmet_caps_confident_grounding` |

**Measured progression on the same task across fixes:** 139s (spiral) → 60s (spiral fixed)
→ 34s to first blocking action (filler stripped). Wasted wall-clock is bounded; the
engine no longer flails.

## Known-hard, tracked (not yet reliable)

- **Custom Electron / web-app widgets that expose text but no clickable geometry** (e.g.
  Spotify search-result playlist items). The text is perceived (OCR/UIA) but does not
  resolve to a clickable position, so `find` returns `None`. Grounding these without
  app-specific hardcoding (forbidden) is open work: candidate directions are
  keyboard-navigation fallback (Tab/Enter to activate a focused-but-unpositioned item)
  and OCR-bbox click when a named element lacks geometry.

## The benchmark: `evals/suite_reliability.json`

Eight representative real desktop workflows (data-entry, app-launch, browser,
extraction, deliverable), scored on **verified outcome against OS state** by the harness:

```powershell
python -m evals.harness run --suite evals/suite_reliability.json --label rel-<date>
```

The number to raise, week over week, is verified success. Every new failure becomes a
row above.
