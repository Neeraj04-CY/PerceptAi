# Chapter 3 — The Universal Perception Layer

> Reasoning quality can never exceed perception quality. Chapter 3 removes
> that ceiling: PerceptAI no longer reads pixels — it understands digital
> environments.

## 1. Architecture review (before)

Until Chapter 2, perception was one source pretending to be a system:

```
screenshot → EasyOCR → text lines → planner prompt
                     ↘ (rare) vision LLM → dicts glued onto OCR positions
```

Everything downstream — planner, healer, evidence collector, memory —
consumed **raw OCR text**. The planner knew where its information came
from (it was told "OCR"), roles and interactivity were guesses, focus and
z-order were invisible, and verification asked "did we send the input?"
rather than "did the world change?".

## 2. Current bottlenecks (found and measured)

1. **OCR as the only source.** 9–13s per CPU pass (measured), no roles,
   no state, no structure. Meanwhile Windows UI Automation delivers 25
   real controls of the foreground window in **67ms** (measured).
2. **Coordinate-space bug.** `_ocr` downscaled screenshots to 960px for
   speed but returned coordinates in *resized-image space* — every click
   landed at a fraction of the true position on screens larger than
   960px. Fixed: coordinates are scaled back, and the OCR provider
   additionally normalizes into the input coordinate space.
3. **OCR deadlock.** `_ocr` held the non-reentrant reader lock while
   calling `_get_reader()`, which acquires the same lock — a guaranteed
   hang on the first real OCR call. Found by the new perception
   benchmark; fixed.
4. **No fusion, no confidence.** Vision elements were bolted onto OCR
   matches; duplicates and contradictions had no arbiter.
5. **Blind verification.** Checks confirmed window existence, never
   world change.

## 3. Perception architecture (after)

```
Perception Sources (plugins)        providers.py
        ↓ observations
Fusion Engine (dedupe + arbitrate)  fusion.py
        ↓ elements + confidence
World Model (one snapshot surface)  world.py
        ↓ WorldState / WorldDiff
Planner · Healer · Verifier · Evidence · Memory · Events
```

The planner receives ONE unified world model. It never learns which
provider saw what — it sees `"Save" [button] 97%`, not "OCR line 14".

## 4. Plugin design

`PerceptionProvider` (providers.py): `name`, `source`, `cost`
(free/cheap/expensive), `available()`, `observe(frame) -> [Observation]`.

- Providers contribute **observations, not decisions**.
- Failures are isolated per provider and recorded in `ProviderReport`s —
  a broken source degrades fidelity, never the run.
- The shared `FrameContext` lets early providers enrich later ones
  (metadata publishes screen geometry → OCR publishes the screenshot →
  vision consumes it).
- Built-ins: `WindowMetadataProvider` (Win32), `UiaProvider` (UI
  Automation, budgeted: max nodes / max depth / wall-clock), `OcrProvider`
  (EasyOCR), `VisionProvider` (Groq vision, expensive tier).
- Future providers = new classes, zero planner changes: browser DOM,
  accessibility trees, clipboard, macOS AX, Android/iOS, remote desktop,
  VM introspection.

## 5. Fusion strategy

Sorted by source trust, positioned observations seed clusters; others
join by **spatial agreement** (IoU ≥ 0.35, or containment + text
agreement — so a text line inside a pane is never swallowed by it).
Position-less vision observations anchor to clusters by text similarity
(exact > containment > fuzzy ratio, threshold 0.82). Each cluster becomes
one `UIElement`: role/name/bbox from the most trusted member that knows
them, attributes merged trust-ascending, every contributing source
recorded. The planner receives the best version — never every version.

## 6. Confidence model

```
observation confidence = provider-native score × source trust
element confidence     = 1 − Π(1 − cᵢ)   (noisy-OR, capped at 0.99)
```

Default trust: os 0.99 · dom 0.98 · uia 0.95 · accessibility/clipboard
0.9 · ocr 0.75 · vision 0.6 · memory 0.5 — a source that guesses can
never outrank one that knows, and agreement compounds certainty without
ever fabricating it. Confidence propagates end-to-end: planner view
(`97%`, `?` marks), click outcomes (`element`, `confidence`, `sources`),
canonical events, TaskResult metadata, and the dashboard. Live
measurement: OCR-only text ≈ 0.4–0.65, UIA-corroborated controls ≥ 0.95.

## 7. World model

`WorldState` (contracts.py): windows (title, z-order, focus, rect,
process, minimized), fused elements (role, name, bbox, confidence,
sources, interactive/enabled/focused/value), focused window + element,
cursor, page context, provider reports, overall confidence.
`WorldDiff`: appeared/disappeared windows, focus moves, element churn,
text similarity → `changed`. Everything is objects, not strings; all
coordinates live in one input coordinate space.

- **Verification** now asks "did the world change?" — first-vs-last
  snapshot comparison (advisory check, honest by design).
- **Healing** first understands WHY: the healer sees the fused world plus
  "since the failed step: …" diff, with failure types extended to
  modal_dialog / loading / focus_lost.
- **Perception memory**: fused elements (with roles) persist per app;
  `recall_interface` feeds "controls seen before in this app" into the
  planner view. Memory informs planning — it never positions a click.

## 8. Repository impact

| Area | Change |
|---|---|
| `perceptai/contracts.py` | + SourceType, BoundingBox, Observation, UIElement, WindowInfo, ProviderReport, WorldState, WorldDiff |
| `perceptai/providers.py` | new — plugin interface + 4 built-in providers |
| `perceptai/fusion.py` | new — fusion + confidence engine (pure logic) |
| `perceptai/world.py` | new — WorldModel: snapshot/diff/find/describe/stats |
| `perceptai/perception.py` | demoted to screenshot+OCR substrate; coordinate + deadlock fixes; vision logic moved to VisionProvider |
| `perceptai/runtime.py` | plans/finds/heals/verifies through the world model only |
| `perceptai/planner.py`, `healer.py` | prompts consume the confidence-annotated world view |
| `perceptai/verification.py` | world-change checks (observe-only, engine passes snapshots) |
| `perceptai/oscontrol.py` | `WindowManager.enumerate()` — z-order/focus/rects/process |
| `perceptai/memory.py` | `recall_interface` read path |
| `perceptai/events.py`, `streaming.py` | `WORLD_SNAPSHOT` canonical event → `world` SSE |
| `evals/perception_bench.py` | new — read-only live perception benchmark |
| `tests/` | +37 tests (fusion, world, providers, streaming, verification, memory, runtime) — 109 total, all green |

Deleted: `perceive_full`, `find_element`, `ElementMatch` (one source of
truth: the world model). No second execution loop; no module-level
mutable state; every new loop budgeted in `EngineConfig`.

## 9. Frontend experience

- **Live World Model viewer** (Run Task): sources with health/latency/
  observation counts, element inspector with per-element confidence
  meters + source badges, snapshot stats.
- **Perception timeline**: one bar per snapshot (height = confidence),
  world-change markers, hover detail.
- **Perception card** (Session detail): provider health, final world
  confidence, elements/windows seen — rendered from
  `result.metadata.perception`.
- Confidence is a magnitude → single-hue meters; provider failures use
  icon + label, never color alone; unknown SSE types are ignored by old
  clients, so the `world` event is safely additive.

## 10. Subscription capability mapping (no gates in code)

Core intelligence (fusion, confidence, world model) is never gated —
these capabilities *naturally* tier:

- **Free**: single execution, basic reports, world model viewer.
- **Builder**: perception timeline history, confidence analytics,
  knowledge/interface memory persistence, execution replay (event log
  is already replayable).
- **Scale**: continuous monitoring (scheduled snapshots + WorldDiff
  alerts), org-wide interface memory, perception benchmarking across
  runners, workflow orchestration.
- **Enterprise**: custom perception providers (the plugin interface is
  the extension point), remote runners streaming WorldStates, policy
  engine over world-state predicates ("never click in a window titled
  X"), audit-grade perception logs, compliance exports.

## 11–13. Implementation, validation, benchmarks

Implemented as above. Validation: 109/109 unit tests (fakes, safe);
live read-only benchmark (`evals/perception_bench.py`, report at
`evals/reports/perception_chapter3-validation.json`):

| Provider | Latency (avg) | Observations | Status |
|---|---|---|---|
| window_metadata | 14ms | 8 windows | OK |
| uia | 67ms | 25 controls | OK |
| ocr | ~13.3s (CPU) | ~143 texts | OK — now the measured bottleneck |

Fusion dedupe 20%; ~178 raw observations → ~140 elements. Run the
desktop eval suites (`suite_core`, `suite_business`) before merging —
they control the real screen, so they are user-executed.

## 14. Future extensions

Concurrent provider execution (thread-pooled `observe`), OCR
region-of-interest / GPU / lighter engines behind the OcrProvider
interface, browser DOM provider (CDP), value patterns from UIA,
element identity tracking across snapshots (stable ids for replay),
multi-monitor coordinate spaces, remote runner protocol streaming
WorldStates, mobile/macOS providers.

## 15. Definition of done — self-review

- *Five years?* Sources will change (mobile, remote, new OSes); the
  Observation→Fusion→WorldState pipeline won't. ✔
- *New provider without rewriting the planner?* One class implementing
  `PerceptionProvider`; the planner is provider-blind. ✔
- *Business workflows more reliable?* UIA gives exact rects/roles/state
  for exactly the SAP/Tally/Excel/ERP class of apps; two real
  click-accuracy bugs (coordinate scaling, deadlock) are fixed;
  verification observes outcomes. ✔
- *Desktops, browsers, cloud runners, mobile?* WorldState is
  platform-neutral; providers are the only platform-specific layer. ✔
