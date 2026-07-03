"""Incremental task planning.

One planner for the whole engine. It plans the NEXT few steps from what
is actually visible on screen, and is re-invoked after anything that
changes the screen. Plans are hypotheses, not scripts.
"""
from __future__ import annotations

from datetime import datetime

from .config import EngineConfig
from .contracts import PlannerOutput, Step, StepResult
from .llm import LLMClient

_ACTIONS = "open_app|navigate_url|focus_window|click|type|clear_type|press|wait|scroll|read_screen"


class Planner:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def plan(
        self,
        instruction: str,
        screen_text: str,
        completed: list[StepResult],
        open_windows: list[str] | None = None,
        source: str = "planner",
    ) -> PlannerOutput:
        now = datetime.now()
        completed_summary = "\n".join(
            f"- {r.step.description} [{r.step.action.value}]: {r.status.value}" for r in completed
        ) or "Nothing completed yet"
        windows_context = ""
        if open_windows:
            windows_context = "\nOpen windows: " + ", ".join(open_windows[:10])

        prompt = f"""You are the PerceptAI planner: a Windows desktop automation planner.
Current time: {now.strftime("%B %d, %Y %I:%M %p")}

GOAL: {instruction}

Already done:
{completed_summary}

Currently visible on screen (OCR):
{screen_text}
{windows_context}

Generate the NEXT steps (maximum {self._config.max_plan_steps}) toward the goal.

Rules:
- Open or focus the target application BEFORE interacting with it.
- Use ONLY text that is ACTUALLY VISIBLE on screen for any "find" field. Never invent placeholder text.
- For dates/times use actual values: {now.strftime("%B %d, %Y")} / {now.strftime("%I:%M %p")}
- Include an "app" field naming the target application in EVERY step.
- Use navigate_url to open websites instead of clicking the address bar.
- read_screen extracts information from the current screen; set "find" to describe what to extract.
- Keep steps atomic.

Return ONLY a valid JSON array:
[
  {{
    "step_number": 1,
    "description": "what this step does",
    "action": "{_ACTIONS}",
    "app": "target app name",
    "url": "full url (navigate_url only)",
    "window": "window title keyword (focus_window only)",
    "find": "EXACT visible text (click) or what to extract (read_screen)",
    "text": "text to type (type only)",
    "key": "key name (press only)",
    "wait": 1.0
  }}
]

Return ONLY the JSON array. No markdown. No explanation."""

        parsed, raw = self._llm.complete_json(prompt, self._config.planner_model)
        if not isinstance(parsed, list):
            return PlannerOutput(ok=False, error="Planner returned no valid step list", raw=raw,
                                 model=self._config.planner_model)

        steps: list[Step] = []
        dropped = 0
        for item in parsed[: self._config.max_plan_steps]:
            if not isinstance(item, dict):
                dropped += 1
                continue
            step = Step.from_planner_dict(item, source=source)
            if step is None:
                dropped += 1
                continue
            steps.append(step)

        if not steps:
            return PlannerOutput(ok=False, error="Planner produced no executable steps", raw=raw,
                                 dropped=dropped, model=self._config.planner_model)
        return PlannerOutput(steps=steps, raw=raw, dropped=dropped, model=self._config.planner_model)

    def extract(self, goal: str, screen_text: str) -> str:
        """Extract specific information from screen text. Empty string if absent."""
        prompt = f"""Extract specific information from screen text.

What to find: {goal}

Screen content:
{screen_text}

Return ONLY the extracted information, nothing else.
If not found, return: NOT_FOUND"""
        result = self._llm.complete_text(prompt, self._config.planner_model, max_tokens=300)
        return "" if result.strip() == "NOT_FOUND" else result.strip()
