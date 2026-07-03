<div align="center">

# PerceptAI

### Universal Perception Layer for AI Agents

*Give AI agents eyes and hands on ANY screen — not just browsers*

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange.svg)]()

</div>

---

## The Problem

AI agents can browse websites. But **75% of real work happens outside browsers** — in desktop apps, legacy enterprise software, government portals, and tools with zero APIs.

Browser Use works on websites via DOM.
**PerceptAI works on anything with pixels.**

---

## What It Does

```python
from perceptai import AgentSession

session = AgentSession()
result = session.run("open notepad and type Hello from PerceptAI")

print(result.status)      # completed | unverified | failed
print(result.summary)     # human-readable outcome
print(result.findings)    # structured data extracted from the screen
print(result.verification.reason)
```

One plain-English instruction in. A structured, verified outcome out.

---

## How It Works

```
Plain English Instruction
        ↓
   Universal Perception       UI Automation + OCR + Vision AI + OS metadata,
        ↓                     fused into ONE confidence-scored world model
   Incremental Planning       Groq LLaMA 3.3 plans from the LIVE world state,
        ↓                     replans after every screen change
   Action Execution           PyAutoGUI + Windows APIs, focus-tracked
        ↓
   Healing & Replanning       failures are diagnosed and recovered, bounded
        ↓
   Outcome Verification       real OS state is checked — success is never assumed
        ↓
   Structured TaskResult      status · summary · findings · verification · events
```

The engine emits one canonical event stream consumed by the CLI, the API's
SSE endpoint, the dashboard and the database — observability is built in,
not bolted on.

---

## Quick Start

```bash
# Clone
git clone https://github.com/Neeraj04-CY/PerceptAi
cd PerceptAi

# Setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Configure
echo GROQ_API_KEY=your_key_here > .env

# Run (controls your real mouse and keyboard!)
python examples/natural_language_demo.py
```

Get your free Groq API key at [console.groq.com](https://console.groq.com)

---

## Architecture

```
perceptai/               the engine — ONE execution runtime
├── session.py           AgentSession: composition root, all state session-scoped
├── runtime.py           ExecutionEngine: perceive → plan → act → verify loop
├── contracts.py         typed contracts (Task, TaskResult, Step, Finding, ...)
├── events.py            canonical event stream (EventBus)
├── providers.py         perception plugins (UI Automation, OCR, vision, Win32)
├── fusion.py            multi-source fusion + confidence engine
├── world.py             the world model — the ONE perception surface
├── perception.py        screenshot + OCR substrate
├── planner.py           incremental LLM planning from the live world state
├── healer.py            failure diagnosis and recovery
├── verification.py      side-effect-free outcome verification
├── actions.py           input primitives (click, type, press, scroll)
├── oscontrol.py         generic app launching + window management
└── memory.py            persistent interface/task memory (SQLite)

api/                     FastAPI SaaS layer (auth, keys, sessions, SSE streaming)
frontend/                Next.js dashboard
evals/                   outcome-based evaluation harness + task suites
tests/                   unit tests (fully faked — safe to run anywhere)
```

---

## Testing & Evaluation

```bash
python -m pytest tests/ -q                                    # safe: fakes only

# Live evaluation — controls the real desktop, run deliberately:
python -m evals.harness run --suite evals/suite_core.json --label mychange
python -m evals.harness compare evals/reports/before.json evals/reports/mychange.json
```

Success is measured by **business outcomes** verified against real OS state
(window exists, text visible on screen, file contents) — never by step counts.

---

## Stack

| Component | Technology |
|-----------|-----------|
| Vision AI | Groq LLaVA (llama-4-scout) |
| Task Planning | Groq LLaMA 3.3 70B |
| OCR | EasyOCR |
| Actions | PyAutoGUI + pyperclip |
| OS Control | Python ctypes (Windows) |

---

## Roadmap

- [x] Unified session-scoped runtime with typed contracts
- [x] Canonical event stream (CLI / SSE / dashboard / DB from one source)
- [x] Outcome-based evaluation harness
- [ ] Memory-first planning (recall interface maps and task patterns)
- [ ] Additional perception backends (Windows UI Automation, browsers)
- [ ] Control plane + local runners (cloud API driving user machines)
- [ ] Workflow composition and scheduled tasks
- [ ] Structured reports as a first-class deliverable

---

## Built By

**Neeraj** — Computer Engineering Student, Maharashtra, India
Building the perception layer the agent ecosystem is missing.

[GitHub](https://github.com/Neeraj04-CY/PerceptAi) • [LinkedIn](https://www.linkedin.com/in/neerajpatil-cs/)

---

## License

Apache 2.0 — free to use, modify, and build on.
