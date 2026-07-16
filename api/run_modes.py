"""Run controls the user actually holds: model and execution mode.

Both are DATA mapped onto the engine's existing configuration — the same
provider routing (llm.py) and budget knobs (EngineConfig) every run
already uses. Nothing here forks the runtime, and nothing here may touch
verification: a mode can spend more or less on perception, retries and
models, but honesty is not a dial.

Only real options are offered. The engine routes to Anthropic (frontier)
and Groq (fast) today; adding a provider (OpenAI/Gemini/local) is a new
ModelProvider in the engine, at which point it earns a row here.
"""
from __future__ import annotations

from typing import Optional

# model choice -> engine overrides. "auto" keeps the engine's capability-
# aware routing; the rest force a provider family. Only providers actually
# configured are offered to the user (the /models endpoint filters).
MODELS: dict[str, dict] = {
    "auto": {},
    "claude": {"model_provider": "anthropic"},
    "gpt": {"model_provider": "openai"},
    "gemini": {"model_provider": "gemini"},
    "groq": {"model_provider": "groq"},
    "local": {"model_provider": "ollama"},
}

# execution mode -> engine overrides. Budgets and routing ONLY —
# pinned by test: no verification/honesty keys may ever appear here.
MODES: dict[str, dict] = {
    "balanced": {},
    # Spend less: fewer retries and replans; adaptive perception already
    # skips OCR when structure is rich.
    "fast": {"find_retries": 2, "max_replans": 2, "max_healing_attempts": 1},
    # Spend more: deeper retries, more replans, frontier reasoning.
    "max_reliability": {"find_retries": 4, "max_replans": 5,
                        "max_healing_attempts": 3, "model_provider": "anthropic"},
    # Privacy is enforced at the egress checkpoint (screenshots never
    # leave this machine), not by weakening anything else.
    "private": {},
}

# Keys a mode is ALLOWED to override. The test suite pins this allowlist —
# adding a verification knob here should fail review loudly.
ALLOWED_OVERRIDE_KEYS = {
    "model_provider", "find_retries", "max_replans", "max_healing_attempts",
}

_EGRESS_STRICTNESS = ["allow", "redact", "local_only", "deny"]


def overrides_for(model: Optional[str], exec_mode: Optional[str]) -> dict:
    """Engine config overrides for a run. Unknown values fall back to
    auto/balanced — a typo never breaks a run."""
    out: dict = {}
    out.update(MODES.get((exec_mode or "balanced").lower(), {}))
    out.update(MODELS.get((model or "auto").lower(), {}))
    return out


def egress_for(workspace_egress: Optional[dict], exec_mode: Optional[str]) -> Optional[dict]:
    """Private mode raises egress to local_only — never lowers it. The
    workspace policy stays the floor: deny remains deny."""
    if (exec_mode or "").lower() != "private":
        return workspace_egress
    current = str((workspace_egress or {}).get("mode", "allow"))
    current_rank = _EGRESS_STRICTNESS.index(current) if current in _EGRESS_STRICTNESS else 0
    if current_rank >= _EGRESS_STRICTNESS.index("local_only"):
        return workspace_egress  # already as strict or stricter
    return {**(workspace_egress or {}), "mode": "local_only"}
