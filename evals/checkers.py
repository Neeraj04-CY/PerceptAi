"""Outcome checkers: assert business outcomes against REAL OS state.

Checkers are runtime-agnostic — they inspect windows, screen text and
files, never the runtime's self-reported step statuses. This is what
lets the harness compare different runtimes honestly, and measure
whether the runtime's own verification tells the truth.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class CheckOutcome:
    name: str
    passed: bool
    detail: str = ""


def _resolve_template(text: str) -> str:
    now = datetime.now()
    return (
        text.replace("{{year}}", now.strftime("%Y"))
        .replace("{{month_name}}", now.strftime("%B"))
    )


def check_window_exists(spec: dict) -> CheckOutcome:
    from perceptai.oscontrol import WindowManager
    keyword = spec["keyword"]
    title = WindowManager().exists(keyword)
    return CheckOutcome(
        name=f"window_exists:{keyword}",
        passed=title is not None,
        detail=title or "no matching window",
    )


def check_screen_contains(spec: dict) -> CheckOutcome:
    """OCR the current screen and look for expected text (case-insensitive)."""
    from perceptai import AgentSession, EngineConfig
    text = _resolve_template(spec["text"]).lower()
    session = AgentSession(EngineConfig.from_env())
    perception = session.perception.perceive_fast(force_refresh=True)
    screen = perception.screen_text.lower()
    return CheckOutcome(
        name=f"screen_contains:{spec['text'][:40]}",
        passed=text in screen,
        detail="found" if text in screen else f"absent from {len(perception.text_blocks)} OCR blocks",
    )


def check_file_contains(spec: dict) -> CheckOutcome:
    path = Path(_resolve_template(spec["path"])).expanduser()
    text = _resolve_template(spec["text"])
    if not path.exists():
        return CheckOutcome(name=f"file_contains:{path.name}", passed=False, detail="file missing")
    content = path.read_text(encoding="utf-8", errors="replace")
    return CheckOutcome(
        name=f"file_contains:{path.name}",
        passed=text in content,
        detail="found" if text in content else "text absent",
    )


def check_finding_contains(spec: dict, result_dict: dict | None) -> CheckOutcome:
    """Checks the returned TaskResult findings (structured-output quality)."""
    expected = _resolve_template(spec["text"]).lower()
    findings = (result_dict or {}).get("findings") or []
    values = " ".join(str(f.get("value", "")) for f in findings).lower()
    return CheckOutcome(
        name=f"finding_contains:{spec['text'][:40]}",
        passed=expected in values,
        detail=f"{len(findings)} finding(s)",
    )


CHECKERS: dict[str, Callable] = {
    "window_exists": lambda spec, result: check_window_exists(spec),
    "screen_contains": lambda spec, result: check_screen_contains(spec),
    "file_contains": lambda spec, result: check_file_contains(spec),
    "finding_contains": check_finding_contains,
}


def run_checkers(specs: list[dict], result_dict: dict | None) -> list[CheckOutcome]:
    outcomes = []
    for spec in specs:
        kind = spec.get("type", "")
        fn = CHECKERS.get(kind)
        if fn is None:
            outcomes.append(CheckOutcome(name=f"unknown:{kind}", passed=False, detail="unknown checker"))
            continue
        try:
            outcomes.append(fn(spec, result_dict))
        except Exception as e:
            outcomes.append(CheckOutcome(name=kind, passed=False, detail=f"checker error: {e}"))
    return outcomes
