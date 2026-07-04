"""Mission decomposition: one prompt becomes a graph of work orders.

Exactly one LLM call at the boundary, against the live capability
vocabulary from the registry — decomposition is architecture, never a
human-written workflow. The output passes deterministic validation
(capability whitelist, order caps, cycle breaking happens in WorkGraph)
and degrades to a single work order on any failure: a mission can never
be worse than a single Chapter-4 task.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import GoalSpec
from .contracts import WorkforceConfig, WorkOrder


class MissionPlanner:
    def __init__(self, config: WorkforceConfig, llm):
        self._config = config
        self._llm = llm

    def decompose(self, instruction: str, goal: Optional[GoalSpec],
                  capabilities: list[str],
                  known_facts: Optional[dict] = None) -> list[WorkOrder]:
        parsed = self._ask(instruction, goal, capabilities, known_facts or {})
        orders = self._validate(parsed, capabilities)
        if not orders:
            orders = [self._fallback(instruction, goal, capabilities)]
        return orders

    # ------------------------------------------------------------ boundary

    def _ask(self, instruction: str, goal: Optional[GoalSpec],
             capabilities: list[str], known_facts: dict) -> Optional[list]:
        goal_block = ""
        if goal is not None:
            goal_block = (
                f"Deliverable: {goal.deliverable or 'not specified'}\n"
                f"Objectives: {'; '.join(goal.objectives[:8])}\n"
                f"Entities: {', '.join(goal.entities[:8])}\n"
            )
        facts_block = ""
        if known_facts:
            listed = "; ".join(f"{k}={v}" for k, v in list(known_facts.items())[:8])
            facts_block = f"Already known (do not re-research): {listed}\n"

        prompt = f"""You are the mission planner of an autonomous business workforce.

Mission: {instruction}
{goal_block}{facts_block}
Available worker capabilities (use ONLY these): {", ".join(capabilities)}

Decompose the mission into independent work orders that can run in
parallel unless one genuinely needs another's output. Return ONLY a
valid JSON array (max {self._config.max_work_orders} items):
[
  {{
    "objective": "one plain-English objective a worker can execute alone",
    "capability": "one capability from the list above",
    "entities": ["companies/products/documents this objective is about"],
    "produces": ["short_keys_of_information_this_yields"],
    "requires": ["keys_it_needs_from_other_orders (usually empty)"],
    "priority": 1-9 (1 = most important),
    "expected_duration_s": 120
  }}
]

Rules:
- Prefer several small parallel objectives over one large sequential one.
- "requires" creates a dependency; leave it empty unless truly needed.
- Include one "memory_recall" order first when past knowledge could help.
- Include one "verification" order that requires the main findings when
  the mission produces a report.
Return ONLY the JSON array."""

        try:
            parsed, _raw = self._llm.complete_json(
                prompt, self._config.model, max_tokens=1200)
        except Exception:
            return None
        return parsed if isinstance(parsed, list) else None

    # ---------------------------------------------------------- validation

    def _validate(self, parsed: Optional[list],
                  capabilities: list[str]) -> list[WorkOrder]:
        if not parsed:
            return []
        available = set(capabilities)
        orders: list[WorkOrder] = []
        for raw in parsed[: self._config.max_work_orders]:
            if not isinstance(raw, dict):
                continue
            objective = str(raw.get("objective", "")).strip()
            capability = str(raw.get("capability", "")).strip().lower()
            if not objective or capability not in available:
                continue  # unknown capabilities are dropped, never guessed
            try:
                priority = max(1, min(9, int(raw.get("priority", 5))))
            except (TypeError, ValueError):
                priority = 5
            try:
                duration = max(1.0, float(raw.get("expected_duration_s", 60)))
            except (TypeError, ValueError):
                duration = 60.0
            orders.append(WorkOrder(
                objective=objective,
                capability=capability,
                entities=self._strings(raw.get("entities")),
                produces=self._keys(raw.get("produces")),
                requires=self._keys(raw.get("requires")),
                priority=priority,
                expected_duration_s=duration,
            ))
        return orders

    def _fallback(self, instruction: str, goal: Optional[GoalSpec],
                  capabilities: list[str]) -> WorkOrder:
        """Degrade path: the whole mission as one order, capability chosen
        from the goal shape and what is actually registered."""
        preference = ["desktop"]
        if goal is not None:
            if goal.output_format == "report":
                preference = ["research", "browser", "desktop"]
            elif goal.output_format == "data":
                preference = ["extraction", "research", "desktop"]
        capability = next((c for c in preference if c in capabilities),
                          capabilities[0] if capabilities else "desktop")
        return WorkOrder(
            objective=instruction,
            capability=capability,
            entities=list(goal.entities) if goal is not None else [],
            priority=1,
        )

    @staticmethod
    def _strings(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()][:8]

    @staticmethod
    def _keys(value) -> list[str]:
        if not isinstance(value, list):
            return []
        keys = []
        for v in value:
            key = "_".join(str(v).strip().lower().split())
            if key:
                keys.append(key[:60])
        return keys[:8]
