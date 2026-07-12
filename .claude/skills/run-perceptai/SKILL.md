---
name: run-perceptai
description: Build, run, screenshot, smoke-test and drive the PerceptAI platform (FastAPI backend + Next.js dashboard + Python automation engine). Use when asked to run/start/launch PerceptAI, screenshot the dashboard, verify the app works end-to-end, or test the engine.
---

# Run PerceptAI

PerceptAI is three runnable surfaces in one repo:

| Surface | What it is | How you drive it |
|---|---|---|
| **api/** | FastAPI control plane (:8000), real Supabase | `uvicorn`, then `curl` / the driver |
| **frontend/** | Next.js dashboard (:3000) | **`driver.mjs`** (Playwright) — the agent path |
| **perceptai/**, **runner/**, **evals/** | The automation engine | `pytest` + **simulated** benches only |

The agent path is **`.claude/skills/run-perceptai/driver.mjs`** — it signs in against the *live* backend (real JWT, real Supabase), drives the *real* dashboard, and screenshots it. No mocks.

> ⚠️ **READ THIS FIRST — the engine takes over the real mouse and keyboard.**
> Executing a task (`/dashboard/run`, `examples/natural_language_demo.py`, `python -m evals.harness`, `perceptai-runner`) **moves the physical cursor and types on the real screen of this machine.** Never launch those to "check if it works." Everything in this skill is safe: the driver only does CRUD, and the benches below are fully simulated.

All paths are relative to the repo root.

## Prerequisites

Already present in this checkout: `.venv311` (Python deps), `frontend/node_modules`, `api/.env` (Supabase + JWT + Groq keys), `frontend/.env.local` (points the UI at `127.0.0.1:8000`).

Playwright is **not** a project dependency — the driver owns it. One-time:

```bash
cd .claude/skills/run-perceptai && npm install
```

## Run (agent path)

Three terminals — or background the first two.

**1. Backend** (must run from *inside* `api/` — imports are cwd-relative):

```bash
cd api && ../.venv311/Scripts/python -m uvicorn main:app --port 8000
```

**2. Frontend:**

```bash
cd frontend && npm run dev
```

**3. Drive it:**

```bash
cd .claude/skills/run-perceptai

node driver.mjs health     # API + db + engine status
node driver.mjs auth       # real signup/signin -> prints a JWT
node driver.mjs shot       # screenshot all 9 dashboard pages
node driver.mjs shot studio org      # ...or just some
node driver.mjs flow       # real click-through: template -> new workflow
node driver.mjs smoke      # health + all screenshots + flow  ← use this
```

`smoke` is the one-shot verification. Screenshots land in `.claude/skills/run-perceptai/shots/`. **Open one and look at it** — a green "ok" only means no page error, not that the page rendered.

Verified output:

```
API health: {"status":"healthy","database":true,"engine":true,"execution_host":true,"scheduler":false,...}
dashboard  ok  -> shots/dashboard.png
studio     ok  -> shots/studio.png
...
created workflow: http://localhost:3000/dashboard/studio/c957e0f0-...
instruction loaded: "In {{erp}}, create and post a vendor invoice for vendor {{vendor}}..."

SMOKE OK
```

Pages: `dashboard operations templates approvals answers settings analytics runners org keys`.
Env overrides: `API=` (default `http://127.0.0.1:8000`), `WEB=` (default `http://localhost:3000`).

## Test (safe — no screen control)

```bash
.venv311/Scripts/python -m pytest tests/ -q                      # 614 passed
.venv311/Scripts/python -m evals.reasoning_bench --label check   # simulated
.venv311/Scripts/python -m evals.critic_bench                    # simulated A/B
.venv311/Scripts/python -m runner --doctor                       # read-only host check
```

`reasoning_bench` and `critic_bench` run the **real** runtime against scripted screens — no mouse, no LLM, safe anywhere. `evals/harness.py` is **not** in this list on purpose: it drives the real desktop.

## Run (human path)

Same two servers, then open <http://localhost:3000> and sign in. Only useful if you want to click **Run** — which controls this machine's screen. Ctrl-C to stop.

## Gotchas

- **The engine controls the real screen.** Repeated because it's the one that bites: never run a task/demo/harness to test things. PyAutoGUI failsafe = slam the cursor into a screen corner to abort.
- **Auth needs BOTH a cookie and localStorage.** `middleware.ts` gates `/dashboard` on the `perceptai_token` **cookie**; the app reads the JWT from **localStorage**. Set only one and you silently bounce to `/signin`. The driver sets both.
- **`networkidle` is not enough — you will screenshot skeletons.** Every page is a client component that fetches after mount and renders `animate-pulse` placeholders. Studio and the workflow editor do this *reliably*. The driver's `settle()` waits for `.animate-pulse` to hit zero. Playwright locators auto-wait, so an assertion can pass while the *screenshot* still shows a skeleton — that bug is easy to ship.
- **The `flow` command is only idempotent because it targets a role.** After it runs once, the workflow it created appears in "Your workflows", so the template's title matches **twice** → `getByText()` throws a strict-mode violation. Template cards are `<button>`, saved workflows are `<a>`; the driver uses `getByRole("button", ...)`.
- **`frontend/.env` points at production Railway.** `frontend/.env.local` overrides it to `127.0.0.1:8000` (Next.js prefers `.env.local`). If `.env.local` goes missing, the local dashboard silently talks to the *production* API.
- **`"scheduler": false` in health is normal** — it means `ENABLE_SCHEDULER` isn't set. `database:true, engine:true` are the ones that matter.
- The driver writes to the **real** Supabase (signup + workflow rows) under a throwaway account, `agent-smoke@perceptai.dev`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ERR_MODULE_NOT_FOUND: playwright` | `cd .claude/skills/run-perceptai && npm install`. Playwright is *not* in `frontend/node_modules`. |
| Screenshot shows grey pulsing boxes | You screenshotted skeletons. Use the driver (it calls `settle()`), don't hand-roll a `waitForTimeout`. |
| `strict mode violation: resolved to 2 elements` | Two things share that text (see Gotchas). Disambiguate by role. |
| Driver: `BOUNCED-TO-SIGNIN` | Backend down, or the cookie wasn't set. Check `node driver.mjs health` first. |
| `ModuleNotFoundError` from uvicorn | You started it from the repo root. It must run from *inside* `api/`. |
| Dashboard loads but every panel is empty | The UI is hitting production. Confirm `frontend/.env.local` exists with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`. |
