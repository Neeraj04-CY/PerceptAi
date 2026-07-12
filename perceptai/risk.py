"""Risk assessment — the trust layer's "what could go wrong" signal.

Deterministic, observe-only, no LLM calls (risk detection cannot cost a
per-cycle model call). Every imminent action is inspected against a small
taxonomy of consequential intents; matches become RiskFlags the cockpit
shows the operator. Risk is *always observed and emitted*; it only *gates*
execution when a workspace sets an approval threshold (policy as data).

New risk kinds are new keyword sets here — never a special case in the
runtime. The runtime asks `assess()` and `requires_approval()`; it never
knows what "financial" means.
"""
from __future__ import annotations

from typing import Optional

from .config import EngineConfig
from .contracts import ActionType, RiskFlag, RiskLevel, Step, WorldState
from .fusion import normalize_text

_INPUT_ACTIONS = {
    ActionType.CLICK, ActionType.TYPE, ActionType.CLEAR_TYPE, ActionType.PRESS,
}

# Intent taxonomy: (kind, level, phrases). Phrases are matched against the
# normalized step description + its text/find/window params. Ordered most to
# least severe; the highest level per kind wins.
_TAXONOMY: list[tuple[str, RiskLevel, tuple[str, ...]]] = [
    ("irreversible", RiskLevel.HIGH, (
        "delete", "remove", "erase", "uninstall", "format", "wipe",
        "drop table", "discard", "clear all", "empty trash", "permanently",
        "delete account", "close account", "deactivate", "revoke", "factory reset",
    )),
    ("financial", RiskLevel.HIGH, (
        "pay", "payment", "purchase", "buy now", "checkout", "place order",
        "confirm order", "transfer", "send money", "wire ", "withdraw",
        "confirm payment", "complete purchase", "subscribe",
    )),
    ("credentials", RiskLevel.HIGH, (
        "password", "passcode", "pin", "ssn", "social security", "card number",
        "credit card", "cvv", "secret", "api key", "private key", "seed phrase",
    )),
    ("communication", RiskLevel.MEDIUM, (
        "send email", "send message", "send ", "publish", "post ", "submit",
        "share", "reply", "forward", "tweet", "broadcast",
    )),
]

_LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

_KIND_SUMMARY = {
    "irreversible": "This action may be irreversible",
    "financial": "This action may move money or complete a purchase",
    "credentials": "This action involves credentials or secrets",
    "communication": "This action sends or publishes content",
    "low_confidence": "Acting while perception confidence is low",
    "prompt_injection": "The screen is attempting to instruct the agent",
}


class RiskAssessor:
    """Owned by AgentSession, constructor-injectable. Pure computation over
    the imminent step and the last observed world."""

    def __init__(self, config: EngineConfig):
        self._config = config

    def assess(self, step: Step, world: Optional[WorldState]) -> list[RiskFlag]:
        if not self._config.risk_detection_enabled:
            return []
        if step.action not in _INPUT_ACTIONS:
            return []

        haystack = " ".join(normalize_text(str(v)) for v in (
            step.description,
            step.params.get("find", ""),
            step.params.get("text", ""),
            step.params.get("window", ""),
            step.params.get("app", ""),
            step.params.get("key", ""),
        ) if v)

        flags: list[RiskFlag] = []
        for kind, level, phrases in _TAXONOMY:
            hit = next((p for p in phrases if normalize_text(p) in haystack), None)
            if hit is not None:
                flags.append(RiskFlag(
                    kind=kind, level=level,
                    summary=_KIND_SUMMARY[kind],
                    detail=f"matched '{hit.strip()}' in: {step.description}",
                ))

        # Acting while the world model is uncertain is its own risk — a wrong
        # click on a misread screen can cause real damage.
        if world is not None and world.confidence < self._config.low_confidence_threshold:
            flags.append(RiskFlag(
                kind="low_confidence", level=RiskLevel.MEDIUM,
                summary=_KIND_SUMMARY["low_confidence"],
                detail=f"world confidence {world.confidence:.2f} < "
                       f"{self._config.low_confidence_threshold:.2f}",
            ))

        # Chapter IX — capability confinement. The screen this action will touch
        # is trying to instruct the agent. Detection is not the barrier (the
        # fence and the frozen goal are), but a hostile screen makes every
        # consequential action worth a human's attention: content attempting
        # goal replacement or credential theft raises the action to HIGH so the
        # workspace's existing approval threshold gates it.
        report = getattr(world, "injection", None) if world is not None else None
        if report is not None and report.tainted:
            flags.append(RiskFlag(
                kind="prompt_injection",
                level=RiskLevel.HIGH if report.critical else RiskLevel.MEDIUM,
                summary=_KIND_SUMMARY["prompt_injection"],
                detail=report.summary(),
            ))
        return flags

    def peak_level(self, flags: list[RiskFlag]) -> RiskLevel:
        return max((f.level for f in flags), key=lambda lv: _LEVEL_ORDER[lv],
                   default=RiskLevel.LOW)

    def requires_approval(self, flags: list[RiskFlag]) -> bool:
        """Policy as data: gate only when the workspace set a threshold and a
        flag meets or exceeds it. Off by default (threshold ''), so a run is
        never blocked unless someone asked for governance."""
        threshold = (self._config.approval_risk_threshold or "").strip().lower()
        if not threshold or not flags:
            return False
        try:
            floor = _LEVEL_ORDER[RiskLevel(threshold)]
        except ValueError:
            return False
        return any(_LEVEL_ORDER[f.level] >= floor for f in flags)
