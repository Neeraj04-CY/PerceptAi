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

    def diagnose(self, failed_step: Step, error_info: str, world_view: str) -> HealingPlan:
        """Diagnose a failure. Returns the most likely explanation as the
        primary plan, with the remaining ranked explanations as
        `alternatives` — one LLM call, multiple live hypotheses."""
        step_json = json.dumps(
            {"action": failed_step.action.value, "description": failed_step.description, **failed_step.params},
            indent=2,
        )
        prompt = f"""You are an AI agent debugger for Windows automation.

A step in an automation task just failed. Consider EVERY plausible
explanation before committing to one — the obvious cause is often wrong.

Failed step:
{step_json}

Error info: {error_info}

Current world state (fused multi-source perception, with what changed since the failure):
{world_view}

Common causes to consider: the element disappeared or moved, the window
changed or closed, a modal dialog or permission prompt is blocking the
screen, the app is still loading, keyboard focus moved elsewhere.

Return ONLY valid JSON — up to 3 hypotheses, MOST LIKELY FIRST:
{{
  "hypotheses": [
    {{
      "diagnosis": "what went wrong in one sentence",
      "failure_type": "element_not_found|app_not_open|wrong_screen|modal_dialog|loading|focus_lost|wrong_app|element_renamed|timeout|other",
      "confidence": 0.8,
      "recovery_steps": [
        {{
          "step_number": 1,
          "description": "what to do to recover",
          "action": "{_ACTIONS}",
          "app": "", "url": "", "window": "", "find": "", "text": "", "key": "", "wait": 1.0
        }}
      ]
    }}
  ]
}}

Rules:
- Only include recovery_steps that are safe given the world state above; an
  unlikely hypothesis may have an empty recovery_steps list.
- Confidence values are independent (they need not sum to 1).
Return ONLY JSON. No explanation."""

        parsed, _raw = self._llm.complete_json(prompt, "heal")
        if not isinstance(parsed, dict):
            return HealingPlan(diagnosis="Unknown failure", failure_type="other")

        raw_hypotheses = parsed.get("hypotheses")
        if not isinstance(raw_hypotheses, list) or not raw_hypotheses:
            # Older single-diagnosis shape: degrade, never raise.
            raw_hypotheses = [parsed]

        plans = [self._parse_one(item) for item in raw_hypotheses if isinstance(item, dict)]
        plans = [p for p in plans if p is not None]
        if not plans:
            return HealingPlan(diagnosis="Unknown failure", failure_type="other")

        primary = plans[0]
        primary.alternatives = plans[1:3]
        return primary

    @staticmethod
    def _parse_one(item: dict) -> HealingPlan | None:
        steps = []
        for raw in item.get("recovery_steps", []) or []:
            if isinstance(raw, dict):
                step = Step.from_planner_dict(raw, source="healer")
                if step is not None:
                    steps.append(step)
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return HealingPlan(
            diagnosis=str(item.get("diagnosis", "")),
            failure_type=str(item.get("failure_type", "other")),
            steps=steps,
            confidence=confidence,
        )
