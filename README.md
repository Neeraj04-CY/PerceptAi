<div align="center">

# PerceptAI

### Universal Perception Layer for AI Agents

*Give AI agents eyes and hands on ANY screen — not just browsers*

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
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
from core.perception import perceive, find_element
from core.planner import plan_task
from core.agent import PerceptAgent
from core.os_control import get_open_windows

# One plain English instruction
instruction = "open notepad and type Hello from PerceptAI"

# PerceptAI handles everything else
screen = perceive()
plan = plan_task(instruction, context, windows)
agent = PerceptAgent(plan["task"])
agent.run(plan["steps"])
```

---

## How It Works

```
Plain English Instruction
	   ↓
   Screen Perception
   (OCR + Vision AI)
	   ↓
    AI Task Planner
   (Groq LLaMA 3.3)
	   ↓
   Action Execution
  (Click, Type, Navigate)
	   ↓
	Task Complete
```

**PERCEIVE** — EasyOCR + Groq Vision reads every element on any screen with real pixel coordinates

**PLAN** — Groq LLaMA 3.3 converts plain English into executable steps

**ACT** — PyAutoGUI executes actions with precision on real screen

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

# Run
python examples/natural_language_demo.py
```

Get your free Groq API key at [console.groq.com](https://console.groq.com)

---

## Example Instructions

```
"open notepad and type Hello World"
"open chrome and go to github.com"  
"search google for autonomous AI agents"
"open calculator"
```

---

## Architecture

```
perceptai/
├── core/
│   ├── perception.py    # Screen capture + OCR + Vision AI
│   ├── action.py        # Click, type, scroll, hotkeys
│   ├── agent.py         # Autonomous execution loop
│   ├── planner.py       # Natural language → action steps
│   └── os_control.py    # App launch, window focus, OS control
└── examples/
    └── natural_language_demo.py
```

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

- [ ] Cloud API — use PerceptAI without local setup
- [ ] pip package — `pip install perceptai`
- [ ] JavaScript SDK
- [ ] Perception memory cache — 10x speed improvement
- [ ] Linux + Mac support
- [ ] Dashboard — session viewer and analytics

---

## Built By

**Neeraj** — Computer Engineering Student, Maharashtra, India  
Building the perception layer the agent ecosystem is missing.

[GitHub](https://github.com/Neeraj04-CY/PerceptAi) • [LinkedIn](https://www.linkedin.com/in/neerajpatil-cs/)

---

## License

MIT — free to use, modify, and build on.
