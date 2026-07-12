# Phase Two, Sprint 4 — Fast, Honest Execution

*A real user ran a real brief. The engine was slow and declared victory without
finishing. This sprint is the autopsy and the fix.*

## The incident

Brief: **"Open Spotify and play Low Cortisol playlist."** Two real runs on this
machine: 112.1s, then 39.9s. Both opened Spotify and clicked the playlist. Neither
pressed Play. Both reported **completed**.

The canonical event record made the diagnosis exact (this is why the evidence spine
exists):

**Wrong outcome.** The goal analyzer correctly derived the criterion *"The Low
Cortisol Playlist is playing."* At verification the LLM judge even said: *"There is
no evidence that the playlist is playing, only that it was clicked"* — check FAILED.
But the planner had already declared the goal achieved (empty replan) after seeing
the playlist page, and for action goals the criterion check is advisory, so support
(a 0.99-grounded click) landed at 0.514 — a hair over the verified floor.
**The engine knew, and finished anyway.**

**Slow.** Per-provider latency from the run:

| Provider | avg/snapshot | observations | share of the 39.9s run |
|---|---|---|---|
| OCR | **7,121 ms** | 372 | **~36 s** (5 snapshots) |
| DOM | 1,511 ms | **0** | ~7.5 s wasted (no browser) |
| UIA | 169 ms | 220 | grounded the click at 0.99 |
| window metadata | 1.5 ms | 45 | — |

The cheap structured source was already sufficient; we paid 40× its cost per frame
for OCR that added nothing, plus a connect-timeout tax for a browser that wasn't
there.

## The fixes (root causes, not symptoms)

1. **Adaptive perception** (`world.py`, `config.py`): OCR is deferred behind the
   structured sources. If UIA/DOM produced ≥ `ocr_skip_min_elements` (12) elements,
   the snapshot skips OCR. Pixels stay the floor: a sparse structured view falls
   back to OCR automatically, a find-miss retries *with* OCR before escalating to
   vision, `read_screen` always includes it (`text_critical`), and full mode is
   unchanged. Config-gated (`adaptive_perception`).
2. **DOM circuit breaker** (`providers.py`): a round that finds no debuggable
   browser backs off for the next 3 snapshots instead of paying the timeout every
   frame — then honestly retries, because a navigate step can spawn a browser
   mid-run.
3. **Completion-gated finish** (`planner.py`): the planner may return `[]` (goal
   achieved) ONLY when every completion criterion is *visibly satisfied in the
   current world state*, with the explicit rule that ongoing states (playing,
   running, submitted, saved) count only when the screen shows that state — a Pause
   control, a confirmation, a changed status. "Clicked toward it" is not "achieved
   it."
4. **Criterion contradiction weight** (`verification.py`): a judged completion
   criterion failing is the user's own definition of done, unmet — it now
   contradicts at 0.5 of its strength (other advisory checks stay at 0.4). The
   Spotify run's exact evidence now computes to **0.448 → UNVERIFIED ("Review")**,
   pinned by a regression test. Action goals keep advisory criteria — a criterion
   failure still never gates alone.

## Measured

- 637 unit tests green (+6: adaptive tiering, OCR fallback, text-critical, DOM
  backoff, the pinned Spotify verdict).
- All four simulated benches unchanged: reasoning honesty 1.0 / confidence error
  0.048 / recovery 1.0; workforce all-pass; enterprise 5/5; critic 3→0 preserved.
  (Simulated screens are UIA-free, so they exercise the OCR-fallback path — the
  tiering cannot silently skip perception there.)
- Real-screen read-only perception bench: DOM backoff confirmed live (one probe,
  then skipped frames); on a UIA-sparse screen OCR correctly still runs — the skip
  engages only when structure is rich, exactly as designed.

## Honest expectations for the next real run

On UIA-rich apps (Spotify exposed 220 structured observations), snapshots drop from
~7–12 s to sub-second, so a run shaped like the incident should fall from ~40 s to
roughly the LLM-call time plus settle delays — and the plan should now include
pressing Play; if it still doesn't, verification will land it at **Review**, not
Completed. That prediction is falsifiable on the next run from the dashboard, and
the Evidence page will show the proof chain either way.
