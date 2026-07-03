"""Failure diagnosis and recovery planning."""
from __future__ import annotations

import json

from .config import EngineConfig
from .contracts import HealingPlan, Step
from .llm import LLMClient

_ACTIONS = "open_app|navigate_url|focus_window|click|type|clear_type|press|wait|scroll|read_screen"


class Healer:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def diagnose(self, failed_step: Step, error_info: str, screen_text: str) -> HealingPlan:
        step_json = json.dumps(
            {"action": failed_step.action.value, "description": failed_step.description, **failed_step.params},
            indent=2,
        )
        prompt = f"""You are an AI agent debugger for Windows automation.

A step in an automation task just failed.

Failed step:
{step_json}

Error info: {error_info}

Currently visible on screen (OCR):
{screen_text}

Diagnose what went wrong and return ONLY valid JSON:
{{
  "diagnosis": "what went wrong in one sentence",
  "failure_type": "element_not_found|app_not_open|wrong_screen|timeout|other",
  "recovery_steps": [
    {{
      "step_number": 1,
      "description": "what to do to recover",
      "action": "{_ACTIONS}",
      "app": "", "url": "", "window": "", "find": "", "text": "", "key": "", "wait": 1.0
    }}
  ],
  "confidence": 0.8
}}

Return ONLY JSON. No explanation."""

        parsed, _raw = self._llm.complete_json(prompt, self._config.planner_model)
        if not isinstance(parsed, dict):
            return HealingPlan(diagnosis="Unknown failure", failure_type="other")

        steps = []
        for item in parsed.get("recovery_steps", []) or []:
            if isinstance(item, dict):
                step = Step.from_planner_dict(item, source="healer")
                if step is not None:
                    steps.append(step)

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return HealingPlan(
            diagnosis=str(parsed.get("diagnosis", "")),
            failure_type=str(parsed.get("failure_type", "other")),
            steps=steps,
            confidence=confidence,
        )
