"""Evidence collection: turn screen observations into typed, sourced facts.

Replaces single-string extraction. Every observation becomes an Evidence
record with kind, label, value, source and confidence — the substrate for
reports, verification and persistent knowledge.
"""
from __future__ import annotations

from .config import EngineConfig
from .contracts import Evidence
from .llm import LLMClient

_KINDS = ("price", "title", "name", "date", "email", "link", "table", "number", "text", "other")


class EvidenceCollector:
    def __init__(self, config: EngineConfig, llm: LLMClient):
        self._config = config
        self._llm = llm

    def collect(self, goal_info: str, screen_text: str, source: str) -> list[Evidence]:
        """Extract structured evidence relevant to goal_info from screen text.
        Returns [] when nothing relevant is visible — never raises."""
        prompt = f"""Extract structured information from screen text.

What to look for: {goal_info}

Screen content (OCR):
{screen_text}

Return ONLY a valid JSON array of evidence items actually present on screen:
[
  {{
    "kind": "price|title|name|date|email|link|table|number|text|other",
    "label": "short machine-friendly label, e.g. 'product_price' or 'page_heading'",
    "value": "the exact extracted value",
    "confidence": 0.9
  }}
]

Rules:
- Extract ONLY information visible in the screen content above. Never invent values.
- Prefer specific kinds (price, date, email) over "text".
- Return [] if the requested information is not on screen.
Return ONLY the JSON array."""

        try:
            parsed, _raw = self._llm.complete_json(prompt, self._config.planner_model, max_tokens=600)
        except Exception:
            return []

        if not isinstance(parsed, list):
            return []

        items: list[Evidence] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            value = str(raw.get("value", "")).strip()
            if not value:
                continue
            kind = str(raw.get("kind", "text")).strip().lower()
            if kind not in _KINDS:
                kind = "other"
            try:
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5
            items.append(
                Evidence(
                    kind=kind,
                    label=str(raw.get("label", goal_info))[:120],
                    value=value,
                    source=source,
                    confidence=confidence,
                )
            )
        return items
