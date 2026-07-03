# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PerceptAI is a screen-driven desktop automation agent for **Windows only**: plain-English instruction → screen perception (EasyOCR + Groq vision) → LLM planning (Groq llama-3.3-70b) → real mouse/keyboard actions (PyAutoGUI + ctypes user32). No DOM access — it works on pixels, so it automates any desktop app. A SaaS layer (FastAPI + Supabase + Next.js dashboard) wraps the engine.

Running the engine or API locally **takes over the real mouse/keyboard and manipulates live windows**. Don't casually run demos, `session.run(...)`, or the eval harness to "test" — they click on the user's actual screen. PyAutoGUI failsafe: slam cursor to a corner to abort. Unit tests (`tests/`) use injected fakes and are always safe to run.

## Product philosophy

- **Pixels, not DOM.** Browser-Use covers websites; PerceptAI targets the ~75% of work in desktop apps, legacy software, and tools with no API. Never add app-specific integrations or special cases (no hardcoded Notepad/Chrome logic) — the generality is the product.
- **Plain English in, structured outcomes out.** Users receive `TaskResult` (status, summary, findings, verification, confidence) — execution logs are for developers.
- **Latency is a feature.** OCR-only perception (`perceive_fast`) is the default; the vision-LLM call is an escalation. Prefer the cheap path first everywhere.
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
- `perception.py` / `actions.py` / `oscontrol.py` — services. Actions are dumb primitives (no focus logic). App launching is generic: PATH → App Paths registry → Win+R; no hardcoded exe paths. Screenshots go to the session workspace (`%TEMP%/perceptai/<id>/`).
- `planner.py` — incremental: plans ≤`max_plan_steps` from the live screen; re-invoked after every launch/navigation and after unhealed failures. Plans are hypotheses, not scripts.
- `healer.py` / `verification.py` — LLM failure diagnosis; verification derives checks from executed steps and only observes (never focuses/changes) OS state.
- `memory.py` — MemoryStore (SQLite at `~/.perceptai/memory.db`). Write hooks are live; the recall path exists but isn't wired into planning yet (future chapter).

Execution loop semantics: perceive → plan → per step (ensure focus → act → emit events) → on failure: heal (bounded) → if unhealed: replan from live screen → if that fails: stop with FAILED. After open_app/navigate_url: settle, then replan. Final status: FAILED (a step failed), COMPLETED (verification passed), or UNVERIFIED (steps ok, verification couldn't confirm).

### API layer (api/)

FastAPI, run from inside `api/` (flat cwd-relative imports). `api/executor.py` is a **thin adapter, not a runtime**: it creates AgentSessions, relays canonical events via `to_legacy_sse`, returns TaskResults, and degrades to a structured error on hosts without desktop deps (Railway). The SSE generator's final `"_result"` item is internal — persisted to the `sessions.result` JSONB column, never forwarded to clients.

Supabase Postgres via service-role key; schema in `database.sql`. Two auth mechanisms: JWT Bearer (custom bcrypt users table) for dashboard/keys routes; `X-API-Key` (`pk_*`, SHA-256 hashed) for execute routes. Plans: free 100 / builder 10k / scale ~unlimited executions per month, enforced pre-execution; every execution is a `sessions` row (audit trail).

**Execution happens on the machine hosting the API.** Cloud deploys have no desktop; real automation requires running the API on a local Windows machine. The long-term design is control-plane + local runners — keep new interfaces compatible with remote, asynchronous execution.

### Evaluation (evals/)

`harness.py` runs task suites and scores **outcomes against real OS state** (window exists, screen contains text, file contents, findings) — runtime-agnostic, so alternative runtimes can be compared via `--runner "<command {instruction}>"`. It also measures `self_report_honesty`: whether the runtime's claimed status matches ground truth. Run a suite before and after any engine change that could affect behavior. Baseline legacy runtime is tagged `chapter0-baseline`.

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
