"""Curated template gallery: the first-run path to value.

Templates are data — a parametrized instruction plus variable schema,
exactly the shape a workflow takes when saved. `{{name}}` slots are
substituted by render_instruction; a missing required variable is an
error, an optional one falls back to its default.
"""
from __future__ import annotations

import re
from typing import Any

_SLOT = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "research-report",
        "name": "Research report",
        "category": "Research",
        "mode": "mission",
        "description": "Multi-specialist research producing a grounded report "
                       "with findings, confidence and sources.",
        "instruction": "Research {{topic}} and produce a structured report with "
                       "key findings, figures and sources.",
        "variables": [
            {"name": "topic", "label": "Topic", "type": "text", "required": True,
             "description": "What to research", "default": ""},
        ],
        "outputs": ["Executive summary", "Key findings", "Evidence with sources"],
    },
    {
        "id": "competitor-pricing",
        "name": "Competitor pricing scan",
        "category": "Research",
        "mode": "mission",
        "description": "Collect current public pricing for a product and its "
                       "competitors, with evidence for every number.",
        "instruction": "Find the current public pricing of {{product}} and its "
                       "main competitors. Capture plan names, monthly prices and "
                       "usage limits, and cite where each number was observed.",
        "variables": [
            {"name": "product", "label": "Product", "type": "text",
             "required": True, "description": "Product or company to benchmark",
             "default": ""},
        ],
        "outputs": ["Pricing comparison", "Plan limits", "Sources"],
    },
    {
        "id": "extract-values",
        "name": "Extract values from an app",
        "category": "Data",
        "mode": "task",
        "description": "Open a source and capture specific fields as typed, "
                       "confidence-scored findings.",
        "instruction": "Open {{source}} and extract the following values: "
                       "{{fields}}. Report each value with where it was found.",
        "variables": [
            {"name": "source", "label": "Source", "type": "text", "required": True,
             "description": "Application, document or page to read", "default": ""},
            {"name": "fields", "label": "Fields", "type": "text", "required": True,
             "description": "Comma-separated values to capture", "default": ""},
        ],
        "outputs": ["Extracted values", "Confidence per value"],
    },
    {
        "id": "data-entry",
        "name": "Data entry with verification",
        "category": "Operations",
        "mode": "task",
        "description": "Enter a record into any application and verify it was "
                       "actually saved before reporting success.",
        "instruction": "Open {{app_name}} and enter the following record: "
                       "{{record}}. Verify the entry was saved and report what "
                       "the application shows afterwards.",
        "variables": [
            {"name": "app_name", "label": "Application", "type": "text",
             "required": True, "description": "Target application", "default": ""},
            {"name": "record", "label": "Record", "type": "text", "required": True,
             "description": "The data to enter", "default": ""},
        ],
        "outputs": ["Entry confirmation", "Verification result"],
    },
    {
        "id": "app-smoke-test",
        "name": "Application smoke test",
        "category": "QA",
        "mode": "task",
        "description": "Launch an application, confirm its main window appears "
                       "and report any errors on screen.",
        "instruction": "Open {{app_name}}, confirm its main window appears and "
                       "no error dialogs are shown, then close it. Report exactly "
                       "what appeared on screen.",
        "variables": [
            {"name": "app_name", "label": "Application", "type": "text",
             "required": True, "description": "Application to test",
             "default": "Notepad"},
        ],
        "outputs": ["Launch result", "Errors observed"],
    },
    {
        "id": "system-check",
        "name": "Windows setting check",
        "category": "Operations",
        "mode": "task",
        "description": "Read a Windows setting and report its current value — "
                       "observation only, nothing is changed.",
        "instruction": "Open Windows Settings, find {{setting}} and report its "
                       "current value without changing anything.",
        "variables": [
            {"name": "setting", "label": "Setting", "type": "text",
             "required": True, "description": "The setting to inspect",
             "default": "display resolution"},
        ],
        "outputs": ["Current value", "Where it was found"],
    },
]


def get_template(template_id: str) -> dict[str, Any] | None:
    return next((t for t in TEMPLATES if t["id"] == template_id), None)


def render_instruction(instruction: str, variables: list[dict[str, Any]],
                       values: dict[str, str]) -> str:
    """Substitute {{slots}} using provided values, falling back to variable
    defaults. Raises ValueError naming every missing required variable."""
    declared = {v["name"]: v for v in variables}
    missing: list[str] = []

    def fill(match: re.Match) -> str:
        name = match.group(1)
        value = values.get(name, "").strip() if values.get(name) else ""
        if not value:
            value = str(declared.get(name, {}).get("default", "") or "").strip()
        if not value:
            if declared.get(name, {}).get("required", False) or name not in declared:
                missing.append(name)
            return ""
        return value

    rendered = _SLOT.sub(fill, instruction)
    if missing:
        raise ValueError(f"missing required variable(s): {', '.join(sorted(set(missing)))}")
    return re.sub(r"\s{2,}", " ", rendered).strip()
