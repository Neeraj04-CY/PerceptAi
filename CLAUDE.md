# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PerceptAI is a screen-driven desktop automation agent for **Windows only**: plain-English instruction → screen perception (EasyOCR + Groq vision) → LLM planning (Groq llama-3.3-70b) → real mouse/keyboard actions (PyAutoGUI + ctypes user32). No DOM access — it works on pixels, so it automates any desktop app. A SaaS layer (FastAPI + Supabase + Next.js dashboard) wraps the engine.

Running the engine or API locally **takes over the real mouse/keyboard and manipulates live windows**. Don't casually run demos or `execute_task` to "test" — it will click on the user's actual screen. PyAutoGUI failsafe: slam cursor to a corner to abort.

## Product philosophy

- **Pixels, not DOM.** Browser-Use covers websites; PerceptAI targets the ~75% of work in desktop apps, legacy software, and tools with no API. Anything visible on screen is automatable. Never add app-specific integrations that bypass perception — the generality is the product.
- **Plain English in, actions out.** The user gives one instruction; planning, element-finding, and recovery are the engine's job, not the user's.
- **Latency is a feature.** OCR-only perception (`perceive_fast`) is the default; the expensive vision-LLM call is a fallback. Downscaled screenshots, cached perception, lazy-loaded models. Prefer the cheap path first everywhere.
- **Self-healing over failing.** When a step fails, diagnose and retry rather than abort. An automation run should degrade, not crash.

## Commands

```powershell
# Engine (repo root) — requires GROQ_API_KEY in .env
.venv\Scripts\activate            # or .venv311; PyTorch/EasyOCR live here
pip install -r requirements.txt
python examples/natural_language_demo.py   # interactive CLI demo (controls the real screen)

# API backend (from api/, has its own .env with Supabase/JWT/Groq keys)
pip install -r api/requirements.txt
uvicorn main:app --reload --port 8000      # run from inside api/ — imports are cwd-relative

# Frontend (from frontend/)
npm install
npm run dev      # Next.js dev server on :3000 (note: "start" also runs dev; "serve" is prod)
npm run build
npm run lint
```

There is no test suite. Deployment: API → Railway via `api/nixpacks.toml`; frontend reads `NEXT_PUBLIC_API_URL`.

## Architecture

### Three copies of the engine — edit `core/`

- `core/` — the live engine. All active development happens here.
- `perceptai/` — pip-package variant (relative imports, friendlier config); an older snapshot that drifts unless deliberately synced.
- `build/lib/` — stale setuptools build output. Never edit.

### Two agent loops — they are different

1. **`core/agent.py` (`PerceptAgent.run`)** — used by the CLI examples. Executes a full pre-made plan from `core/planner.py:plan_task()`, with self-healing on failure (`core/healer.py:diagnose_failure()` — LLM suggests recovery steps, executed if confidence > 0.5, max 2 attempts) and writes screen state to SQLite memory after each step.
2. **`api/executor.py` (`execute_task` / `execute_task_stream`)** — used by the API. Has its own planner (`plan_from_screen`, ≤5 steps at a time) that **replans from a fresh screen read after every `open_app`/`navigate_url`**, adds a `read_screen` action with LLM extraction, injects extracted text into placeholder `type` steps, caps at 12 steps, and ends with heuristic verification (`verify_post_task_state` — window-title matching → status `completed`/`unverified`/`failed`). It reuses `PerceptAgent.execute_step()` for individual actions but not `run()` — so the API path gets **no healing and no memory writes**.

A feature added to one loop does not exist in the other.

### Engine data flow (core/)

- `perception.py` — `perceive_fast()` is the default (OCR-only, 0.8s cache, image downscaled to 960px). `perceive()` adds a Groq llama-4-scout vision call and merges OCR pixel coordinates into vision elements by text match; elements with no OCR match get `position {x:-1, y:-1}` — callers must check `x > 0` before clicking. Screenshot always saved to `temp_screen.png` at repo root.
- `planner.py` / `healer.py` — Groq llama-3.3-70b, prompts demand raw JSON. Plan step vocabulary: `open_app | navigate_url | focus_window | click | type | press | wait` (agent also handles `clear_type`, `scroll`).
- `action.py` — `type_text` pastes via clipboard (pyperclip + Ctrl+V), not keystrokes, to handle special characters.
- `os_control.py` — hardcoded absolute app paths with Win+R fallback; window focus/enumeration via raw ctypes user32.
- `memory.py` — SQLite `perceptai_memory.db`, tables `interface_maps` and `task_patterns`. Currently write-mostly: `recall_element`/`recall_task` exist but aren't wired into the execution loops.

### API layer (api/)

FastAPI, run from inside `api/` (flat cwd-relative imports; reaches `core/` via `sys.path` insertion in `executor.py`). Supabase Postgres via service-role key (`database.py`); schema in `database.sql` — `users`, `api_keys`, `sessions` (steps as JSONB), `usage` (per user-month counter), `plans`/`user_plans` (free 100 / builder 10k / scale ~unlimited executions per month).

Two auth mechanisms:
- **JWT Bearer** (HS256, 7 days, custom bcrypt users table — not Supabase Auth) → dashboard/keys routes.
- **`X-API-Key`** (`pk_*` keys, SHA-256 hash stored, prefix shown) → execute routes. Signup auto-creates a free plan + default key.

Endpoints under `/api/v1`: `auth/signup|signin`, `execute` (sync), `execute/stream` (SSE, defined in `main.py`; executor runs in a worker thread feeding a queue; event types `session_id/plan/step_start/step_complete/replan/log/complete/error`), `dashboard/stats|sessions|usage`, `keys` CRUD (delete = soft-deactivate), `/screenshot`.

**Execution happens on the machine hosting the API.** Deployed to Railway there is no desktop, so real automation only works when the API runs on a local Windows machine.

### Frontend (frontend/)

Next.js 14 App Router + TypeScript + Tailwind + framer-motion + Recharts; dark terminal-green aesthetic. JWT stored in localStorage *and* a `perceptai_token` cookie; `middleware.ts` gates `/dashboard` by decoding JWT expiry client-side. `app/dashboard/page.tsx` (Run Task) consumes the SSE stream directly and auto-creates/caches an API key in localStorage; Sessions/Analytics poll the REST endpoints via `lib/api.ts`.

## Coding standards

**Python (engine + API)**
- Action functions return result dicts — `{"success": bool, ...}` with an `"error"` key on failure — instead of raising. Callers check `result.get("success") is not False`. Follow this convention; don't introduce exception-based control flow into the step-execution path.
- LLM calls: prompt demands "ONLY valid JSON", response is stripped of ``` fences, then `json.loads` with a safe fallback (empty plan / zero-confidence diagnosis). Never let a malformed LLM reply crash a run.
- Expensive resources (EasyOCR reader, Groq clients, Supabase clients) are lazy module-level singletons behind `get_*()` accessors.
- Progress reporting is `print()`-based with two-space indents (the CLI is the UI); no logging framework.
- Timing matters: deliberate `time.sleep` settle-delays after every UI-affecting action are load-bearing, not cruft. Don't strip them; tune them.
- `api/` modules import each other flat (`from config import config`) — the server must run with `api/` as cwd.

**TypeScript (frontend)**
- Client components (`"use client"`) own their data-fetching: `useEffect` + `AbortController`, explicit `loading`/`error`/`unauthorized` state, skeleton/empty/error components per view.
- All API access goes through typed helpers in `lib/api.ts`; API response shapes are mirrored as exported interfaces.
- Styling is Tailwind utility classes with the `cn()` helper (`lib/utils.ts`); UI primitives live in `components/ui/`, feature components under `components/dashboard/**` and `components/landing/**`.

## Engineering principles

- **Perceive → plan → act → verify.** Never act on stale perception: re-read the screen after anything that changes it (app launch, navigation), and replan from what is actually visible. Plans use only text genuinely present on screen — no placeholder targets.
- **Focus before input.** Every click/type/press is preceded by ensuring the target window is focused (`ensure_focus`, `last_app`/`last_window` tracking). Typing into the wrong window is the classic failure mode; guard against it.
- **Bound all loops.** Step caps (12), retry caps (3), healing-attempt caps (2), plan-size caps (5–10). Any new agentic loop needs an explicit budget.
- **Verify outcomes, don't trust step success.** Step results say an action fired, not that it worked — the verification pass checks real OS state (window exists/focusable) before reporting `completed`.
- **Sessions are the audit trail.** Every API execution persists instruction, per-step results, timing, and status to `sessions`; usage is metered per user-month and enforced before execution.
