# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PerceptAI is a screen-driven desktop automation agent for **Windows only**: plain-English instruction → multi-source perception fused into a world model (Windows UI Automation + EasyOCR + Groq vision + Win32 metadata) → LLM planning (Groq llama-3.3-70b) → real mouse/keyboard actions (PyAutoGUI + ctypes user32). Pixels are the floor (any app automates), structured sources raise fidelity when present. A SaaS layer (FastAPI + Supabase + Next.js dashboard) wraps the engine.

Running the engine or API locally **takes over the real mouse/keyboard and manipulates live windows**. Don't casually run demos, `session.run(...)`, or the eval harness to "test" — they click on the user's actual screen. PyAutoGUI failsafe: slam cursor to a corner to abort. Unit tests (`tests/`) use injected fakes and are always safe to run.

## Product philosophy

- **One world model, many sources.** The planner never sees raw OCR or knows which provider observed what — it receives a fused, confidence-scored `WorldState`. Pixels (OCR) keep it universal; UIA/DOM-class sources add fidelity where available. Never add app-specific integrations or special cases (no hardcoded Notepad/Chrome logic) — the generality is the product.
- **Plain English in, structured outcomes out.** Users receive `TaskResult` (status, summary, findings, verification, confidence) — execution logs are for developers.
- **Latency is a feature.** Fast snapshots (free/cheap providers: Win32 metadata, UIA, OCR) are the default; the vision-LLM provider runs only on full-mode escalation. Prefer the cheap path first everywhere.
- **Confidence is honest.** Every observation carries source-weighted confidence; corroboration compounds it (noisy-OR, capped at 0.99); uncertainty propagates to the planner, events and reports. Never fake certainty.
- **Self-healing over failing, honest failure over blind action.** Failed steps are diagnosed and retried, then replanned from the live screen. There are deliberately no blind fallbacks (e.g. no clicking screen-center when an element isn't found).
- **Outcomes, not steps.** Success is measured by whether the user's business outcome was achieved (eval checkers inspect real OS state), never by step/click counts.

## Commands

```powershell
# Engine (repo root) — requires GROQ_API_KEY in .env; .venv311 has the deps
.venv311\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q                    # unit tests, safe (fakes only)
python examples/natural_language_demo.py      # interactive CLI (controls the real screen)

# Evaluation harness (controls the real screen — run deliberately)
python -m evals.harness run --suite evals/suite_core.json --label <name>
python -m evals.harness compare evals/reports/a.json evals/reports/b.json
python -m evals.perception_bench --snapshots 3   # perception-only benchmark: read-only (screenshots + UIA), no input
python -m evals.reasoning_bench --label <name>   # reasoning benchmark: fully simulated, SAFE anywhere (no screen, no LLM)

# API backend (from api/, has its own .env with Supabase/JWT/Groq keys)
pip install -r api/requirements.txt
uvicorn main:app --reload --port 8000         # run from inside api/ — imports are cwd-relative

# Frontend (from frontend/)
npm install
npm run dev      # Next.js dev server on :3000 ("start" also runs dev; "serve" is prod)
npm run build && npm run lint
```

Deployment: API → Railway via `api/nixpacks.toml`; frontend reads `NEXT_PUBLIC_API_URL`.

## Architecture

### One runtime: the `perceptai/` package

There is exactly ONE execution loop in the repository — `perceptai/runtime.py:ExecutionEngine`. Never create a second one; extend this one. `AgentSession` (`session.py`) is the composition root: it owns config, workspace, LLM client, perception, actions, OS control, planner, healer, verifier, memory and the event bus. **No module-level mutable execution state anywhere** — the single sanctioned process-level cache is the EasyOCR model weights (immutable, behind a lock in `perception.py`).

Module map (dependencies flow downward, no cycles):
- `contracts.py` — every cross-boundary type: Task, TaskContext, TaskResult, TaskEvent (in events), Step/StepResult, PlannerOutput, HealingPlan, VerificationResult, ExecutionState, ActionOutcome. Add fields here first; never pass loose dicts across module boundaries.
- `events.py` — EventBus + EventType. The engine emits ONE canonical event stream; all consumers (CLI, SSE, DB, analytics, future runner protocol) derive from it. Never hand-build consumer events.
- `streaming.py` — the only place that knows the dashboard SSE wire schema (`to_legacy_sse`, `legacy_steps`). Pinned by `tests/test_streaming.py`.
- `config.py` — EngineConfig: all budgets, models, settle delays, paths. Every agentic loop must be budgeted (max_steps, max_replans, max_healing_attempts, find_retries).
- `llm.py` — single Groq wrapper; JSON fence-stripping/permissive parsing lives ONLY here. Malformed LLM replies degrade, never raise, in the execution path.
- `providers.py` — the perception plugin surface: `PerceptionProvider` (name, source, cost tier, `available()`, `observe(frame)`). Built-ins: `WindowMetadataProvider` (Win32: windows/z-order/focus/cursor/screen), `UiaProvider` (Windows UI Automation tree of the foreground window, hard-budgeted), `OcrProvider` (wraps PerceptionService, normalizes coords to input space), `VisionProvider` (Groq vision, expensive tier, position-less observations). Providers contribute observations, never decisions; new sources (DOM, macOS, mobile, remote) are new providers — the planner never changes.
- `fusion.py` — FusionEngine: merges multi-source observations into deduped `UIElement`s (spatial IoU/containment + text-similarity clustering), picks role/name/bbox by source trust, combines confidence noisy-OR (capped 0.99). Pure logic, deterministic.
- `world.py` — WorldModel: orchestrates providers under budgets (fast vs full escalation), builds `WorldState`, computes `WorldDiff` between snapshots, resolves element queries (`find` — no blind guesses), serializes the confidence-annotated planner view (`describe`). The ONLY perception surface the runtime consumes.
- `perception.py` / `actions.py` / `oscontrol.py` — primitives. PerceptionService = screenshots + OCR only (one provider's substrate, not the perception system). Actions are dumb primitives (no focus logic). App launching is generic: PATH → App Paths registry → Win+R; no hardcoded exe paths. Screenshots go to the session workspace (`%TEMP%/perceptai/<id>/`).
- `planner.py` — incremental: plans ≤`max_plan_steps` from the live screen; re-invoked after every launch/navigation and after unhealed failures. Goal-aware (objectives, known facts); returns `[]` to signal "goal achieved". Plans are hypotheses, not scripts.
- `goal.py` / `evidence.py` / `reporting.py` — the cognitive layer. GoalAnalyzer turns the instruction into a `GoalSpec` (deliverable, entities, objectives, completion criteria) BEFORE planning; EvidenceCollector turns screen observations into typed, sourced `Evidence`; ReportBuilder assembles the `TaskReport` deliverable, LLM-composing narrative **from collected evidence only** (grounded — never invents facts). All three degrade gracefully on LLM failure; execution is never blocked by cognition.
- `healer.py` / `verification.py` — LLM failure diagnosis from the world view + what changed since the failure (failure types include modal_dialog, loading, focus_lost); verification derives checks from executed steps, compares first-vs-last WorldState ("did the world change?" — advisory), and LLM-judges the goal's completion criteria against evidence (critical for report/data goals, advisory for action goals). Observe-only: never focuses/changes OS state.
- `memory.py` — MemoryStore (SQLite at `~/.perceptai/memory.db`): interface maps (now fed with fused elements + roles; `recall_interface` feeds known controls into the planner's world view — informs planning, never positions a click), task patterns, and the `knowledge` table (evidence persisted as entity-attribute-value, recalled by goal entities to seed future tasks).
- `reasoning.py` + `beliefs.py` / `uncertainty.py` / `hypothesis.py` / `progress.py` / `strategy.py` / `decision.py` / `budgets.py` / `constraints.py` / `recovery.py` — the adaptive reasoning layer (Chapter 4). Deterministic computation over signals the pipeline already produces; LLM calls stay at the plan/diagnose/judge boundaries — never one-per-cycle. `ReasoningEngine` is the stateless orchestrator; per-run state lives in `ReasoningState` (owned by the engine run). BeliefState evolves (noisy-OR support, multiplicative contradiction, full history); UncertaintyTracker emits typed signals that change behavior; HypothesisGenerator keeps multiple failure explanations alive until measured evidence resolves them; DecisionEngine returns one typed `Decision` per cycle with its factors (the runtime executes decisions, never overrides them); RecoveryManager confirms recovery ONLY when the original failure condition measurably cleared, then retries the original step (guarded against double-execution); ConstraintManager is the policy extension point (denials are replanned around, never healed); ExecutionBudgetManager is the single budget ledger.
- `simulation.py` — deterministic in-memory fakes: the ONE substrate for unit tests (via `tests/conftest.py`) and `evals/reasoning_bench.py`. Simulated sessions run the real runtime/world model/reasoning against scripted screens; `fast_config` disables the UIA provider so tests never observe the real desktop.

Execution loop semantics: understand goal (+ recall knowledge) → select strategy → world snapshot → plan → then one typed Decision per cycle: CONTINUE (execute next step) / OBSERVE / ESCALATE_PERCEPTION / VERIFY (reconcile beliefs vs live world) / REPLAN / RECOVER / FINISH / ABORT / NEED_USER. Failures spawn hypotheses → recovery acts on the best one → outcome is measured (condition cleared + original step retried). A replan supersedes a failed step (marked SKIPPED) so verification owns the verdict for the new path. Every decision, belief change, hypothesis and budget snapshot is on the canonical event stream (`metadata.reasoning` carries the replayable summary). Final status: FAILED (unresolved failure/abort), COMPLETED (verification passed), or UNVERIFIED (steps ok, verification couldn't confirm).

Working memory: `TaskContext` is accumulate-only (evidence, sources, notes, facts) — never overwrite, always append. `TaskResult.report` is the business deliverable (executive summary, key findings, evidence, confidence, sources, next actions); the dashboard renders it from `sessions.result`.

### API layer (api/)

FastAPI, run from inside `api/` (flat cwd-relative imports). `api/executor.py` is a **thin adapter, not a runtime**: it creates AgentSessions, relays canonical events via `to_legacy_sse`, returns TaskResults, and degrades to a structured error on hosts without desktop deps (Railway). The SSE generator's final `"_result"` item is internal — persisted to the `sessions.result` JSONB column, never forwarded to clients.

Supabase Postgres via service-role key; schema in `database.sql`. Two auth mechanisms: JWT Bearer (custom bcrypt users table) for dashboard/keys routes; `X-API-Key` (`pk_*`, SHA-256 hashed) for execute routes. Plans: free 100 / builder 10k / scale ~unlimited executions per month, enforced pre-execution; every execution is a `sessions` row (audit trail).

**Execution happens on the machine hosting the API.** Cloud deploys have no desktop; real automation requires running the API on a local Windows machine. The long-term design is control-plane + local runners — keep new interfaces compatible with remote, asynchronous execution.

### Evaluation (evals/)

`harness.py` runs task suites and scores **outcomes against real OS state** (window exists, screen contains text, file contents, findings) — runtime-agnostic, so alternative runtimes can be compared via `--runner "<command {instruction}>"`. It also measures `self_report_honesty` (claimed status vs ground truth) and `avg_confidence_error` (reported confidence vs outcome — calibration). Run a suite before and after any engine change that could affect behavior. Baseline legacy runtime is tagged `chapter0-baseline`.

`reasoning_bench.py` is fully simulated (real runtime + `perceptai.simulation` fakes; no screen, no LLM — safe anywhere, including CI). Ten scripted scenarios (ambiguous labels, delayed apps, changing UI, OCR noise, unrecoverable failures, false action success, policy blocks…) measure recovery success, false-recovery rate, decision stability, confidence calibration, observation efficiency and reasoning consistency (identical scenario → identical decisions). Chapter-4 baseline report: `evals/reports/reasoning_chapter4-validation.json`.

### Frontend (frontend/)

Next.js 14 App Router + TypeScript + Tailwind + framer-motion + Recharts. JWT in localStorage + `perceptai_token` cookie; `middleware.ts` gates `/dashboard`. The Run Task page consumes the SSE stream; Sessions/Analytics poll REST via typed helpers in `lib/api.ts`. UI primitives in `components/ui/`, features under `components/dashboard/**` and `components/landing/**`, Tailwind + `cn()` helper.

## Coding standards

**Python (engine + API)**
- Cross-boundary data uses the dataclasses in `contracts.py`; action primitives return `ActionOutcome`, never raise, in the step-execution path.
- Services are classes owned by AgentSession and constructor-injectable — new dependencies must accept injection so `tests/conftest.py` fakes can replace them.
- Heavy third-party imports (easyocr, groq, pyautogui, PIL, numpy) are lazy — the package must import cleanly on headless hosts.
- Settle `time.sleep`s are load-bearing for real UI; they live in EngineConfig, not inline literals.
- `api/` modules import each other flat (`from config import config`) — the server must run with `api/` as cwd.

**TypeScript (frontend)**
- Client components own their data-fetching: `useEffect` + `AbortController`, explicit loading/error/unauthorized states, skeleton/empty/error components per view.
- All API access through typed helpers in `lib/api.ts`; response shapes mirrored as exported interfaces.

## Engineering principles

- **One source of truth per subsystem.** Never duplicate an execution path; refactor before adding a second version; delete obsolete code instead of accumulating it.
- **Perceive → plan → act → verify.** Never act on stale perception; replan after anything that changes the screen; plans reference only text actually visible.
- **Focus before input; observe-only verification.** Every click/type/press ensures target-window focus first. Verification never has side effects.
- **Bound all loops.** Any new agentic loop needs explicit budgets in EngineConfig.
- **Events are the observability spine.** New runtime behavior emits canonical events; consumers adapt in `streaming.py`, nowhere else.
- **Measure before merging.** Engine behavior changes are validated by unit tests (safe) plus an eval-suite run (user-executed — it controls the desktop).
