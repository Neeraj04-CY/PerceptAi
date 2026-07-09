"""Incremental task planning.

One planner for the whole engine. It plans the NEXT few steps from what
is actually visible on screen, and is re-invoked after anything that
changes the screen. Plans are hypotheses, not scripts.
"""
from __future__ import annotations

from datetime import datetime

from .config import EngineConfig
from .contracts import GoalSpec, PlannerOutput, Step, StepResult, StrategyProfile
from .llm import LLMClient

_ACTIONS = "open_app|navigate_url|focus_window|click|type|clear_type|press|wait|scroll|read_screen"


class Planner:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def plan(
        self,
        instruction: str,
        world_view: str,
        completed: list[StepResult],
        open_windows: list[str] | None = None,
        source: str = "planner",
        goal: GoalSpec | None = None,
        known_facts: dict[str, str] | None = None,
        strategy: StrategyProfile | None = None,
        available_secrets: list[str] | None = None,
    ) -> PlannerOutput:
        now = datetime.now()
        completed_summary = "\n".join(
            f"- {r.step.description} [{r.step.action.value}]: {r.status.value}" for r in completed
        ) or "Nothing completed yet"
        windows_context = ""
        if open_windows:
            windows_context = "\nOpen windows: " + ", ".join(open_windows[:10])

        goal_context = ""
        if goal is not None:
            lines = [f"Deliverable: {goal.deliverable or goal.intent}"]
            if goal.objectives:
                lines.append("Objectives:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(goal.objectives)))
            if goal.required_info:
                lines.append("Information to collect (use read_screen): " + "; ".join(goal.required_info))
            if goal.completion_criteria:
                lines.append("Done when: " + "; ".join(goal.completion_criteria))
            goal_context = "\n" + "\n".join(lines) + "\n"

        facts_context = ""
        if known_facts:
            facts_context = "\nAlready known facts (do NOT re-collect these):\n" + "\n".join(
                f"- {k}: {v[:100]}" for k, v in list(known_facts.items())[:15]
            ) + "\n"

        # Secret NAMES only (never values). The planner references a secret;
        # the engine resolves and types the value at the action layer.
        secrets_context = ""
        if available_secrets:
            secrets_context = (
                "\nAvailable secrets (to enter one, set a type step's \"text\" to "
                "{{secret:NAME}} — NEVER write or guess the actual value):\n"
                + "\n".join(f"- {name}" for name in available_secrets[:15]) + "\n"
            )

        # Strategy tunes HOW this one planner plans; it never becomes a
        # second planner or an app-specific code path.
        strategy_context = ""
        if strategy is not None and strategy.planning_guidance:
            strategy_context = f"\nExecution strategy ({strategy.name}): {strategy.planning_guidance}\n"

        prompt = f"""You are the PerceptAI planner: a Windows desktop automation planner.
Current time: {now.strftime("%B %d, %Y %I:%M %p")}

GOAL: {instruction}
{goal_context}{facts_context}{secrets_context}{strategy_context}
Already done:
{completed_summary}

CURRENT WORLD STATE (fused from UI Automation, OCR and vision; percentages are perception confidence):
{world_view}
{windows_context}

Generate the NEXT steps (maximum {self._config.max_plan_steps}) toward the goal.
If every objective is already achieved, return an empty array: []

Rules:
- Open or focus the target application BEFORE interacting with it.
- For "find" fields use the EXACT name of an element listed in the world state above. Never invent placeholder text.
- Prefer elements with higher confidence; elements marked '?' are uncertain.
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

        if len(parsed) == 0:
            # Deliberate planner signal: the goal is already achieved.
            return PlannerOutput(steps=[], ok=True, raw=raw, model=self._config.planner_model)

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
