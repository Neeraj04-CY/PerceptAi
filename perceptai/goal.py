"""Goal intelligence: understand what the user actually wants BEFORE planning.

The GoalSpec drives the planner (objectives, known facts), verification
(completion criteria) and reporting (deliverable, output format). Analysis
failure degrades to a minimal action-confirmation goal — it never blocks
execution.
"""
from __future__ import annotations

from .config import EngineConfig
from .contracts import GoalSpec
from .llm import LLMClient


class GoalAnalyzer:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def analyze(self, instruction: str, known_facts: str = "") -> GoalSpec:
        known_block = f"\nAlready known from memory:\n{known_facts}\n" if known_facts else ""
        prompt = f"""You are the goal analyst of a business execution agent.

User request: {instruction}
{known_block}
Understand what the user is ACTUALLY trying to achieve. Return ONLY valid JSON:
{{
  "intent": "one sentence: what the user wants to achieve",
  "deliverable": "what the user should receive when this is done",
  "output_format": "report|data|action_confirmation",
  "entities": ["companies, products, people, documents involved"],
  "required_info": ["specific pieces of information that must be collected (empty if none)"],
  "objectives": ["ordered, concrete sub-goals"],
  "completion_criteria": ["observable conditions that mean the task is truly done"],
  "success_definition": "one sentence: how the user would judge success"
}}

Rules:
- output_format is "report" when the user wants findings/comparison/research,
  "data" when they want specific values extracted, "action_confirmation" when
  they want something done (open, type, click, send).
- completion_criteria must be checkable, not vague.
- Do not invent requirements the user did not imply.
Return ONLY JSON."""

        try:
            parsed, _raw = self._llm.complete_json(prompt, self._config.planner_model, max_tokens=600)
        except Exception:
            parsed = None

        if not isinstance(parsed, dict):
            return self._fallback(instruction)

        def _strings(key: str) -> list[str]:
            value = parsed.get(key) or []
            return [str(v) for v in value if str(v).strip()] if isinstance(value, list) else []

        output_format = str(parsed.get("output_format", "action_confirmation")).strip().lower()
        if output_format not in ("report", "data", "action_confirmation"):
            output_format = "action_confirmation"

        return GoalSpec(
            intent=str(parsed.get("intent") or instruction),
            deliverable=str(parsed.get("deliverable", "")),
            output_format=output_format,
            entities=_strings("entities"),
            required_info=_strings("required_info"),
            objectives=_strings("objectives") or [instruction],
            completion_criteria=_strings("completion_criteria"),
            success_definition=str(parsed.get("success_definition", "")),
        )

    @staticmethod
    def _fallback(instruction: str) -> GoalSpec:
        return GoalSpec(intent=instruction, objectives=[instruction])
