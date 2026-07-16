"""The model catalog — capability profiles for every provider/model.

Pure data, no I/O. This is what "real multi-model support" means: each
model advertises its latency, cost, reasoning strength, vision ability
and context window, so the router can choose intelligently and the UI can
show honest options instead of a fake dropdown.

Reasoning/vision strengths are ordinal (1-5), calibrated for the one job
that matters here — planning and grounding a live desktop/browser screen,
not chatbot benchmarks. A model absent from a customer's environment is
never offered (availability is decided in llm.py from real keys); this
file only says what each model IS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ModelProfile:
    provider: str            # anthropic | openai | gemini | groq | ollama
    model: str               # the API model id
    label: str               # human name for the picker
    reasoning: int           # 1..5 — planning/grounding strength
    vision: bool             # can read a screenshot
    context_window: int      # tokens
    cost_tier: str           # free | cheap | mid | premium
    latency_tier: str        # fast | medium | slow
    # Roles this model is a good fit to serve: any of reason|fast|vision.
    serves: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider, "model": self.model, "label": self.label,
            "reasoning": self.reasoning, "vision": self.vision,
            "context_window": self.context_window, "cost_tier": self.cost_tier,
            "latency_tier": self.latency_tier, "serves": list(self.serves),
        }


# The default model each provider uses per tier. Frontier reasoners are
# preferred for planning/grounding; fast models for mechanical extraction;
# vision-capable models for screenshot understanding.
CATALOG: list[ModelProfile] = [
    # ---- Anthropic (Claude) — the reference frontier planner/grounder.
    ModelProfile("anthropic", "claude-sonnet-5", "Claude Sonnet 5",
                 reasoning=5, vision=True, context_window=200_000,
                 cost_tier="premium", latency_tier="medium",
                 serves=("reason", "vision")),
    ModelProfile("anthropic", "claude-opus-4-8", "Claude Opus 4.8",
                 reasoning=5, vision=True, context_window=200_000,
                 cost_tier="premium", latency_tier="slow",
                 serves=("reason", "vision")),
    ModelProfile("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5",
                 reasoning=3, vision=True, context_window=200_000,
                 cost_tier="cheap", latency_tier="fast",
                 serves=("fast", "vision")),
    # ---- OpenAI (GPT).
    ModelProfile("openai", "gpt-5.6", "GPT-5.6",
                 reasoning=5, vision=True, context_window=400_000,
                 cost_tier="premium", latency_tier="medium",
                 serves=("reason", "vision")),
    ModelProfile("openai", "gpt-5.6-mini", "GPT-5.6 mini",
                 reasoning=3, vision=True, context_window=400_000,
                 cost_tier="cheap", latency_tier="fast",
                 serves=("fast", "vision")),
    # ---- Google (Gemini).
    ModelProfile("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro",
                 reasoning=5, vision=True, context_window=1_000_000,
                 cost_tier="mid", latency_tier="medium",
                 serves=("reason", "vision")),
    ModelProfile("gemini", "gemini-2.5-flash", "Gemini 2.5 Flash",
                 reasoning=3, vision=True, context_window=1_000_000,
                 cost_tier="cheap", latency_tier="fast",
                 serves=("fast", "vision")),
    # ---- Groq (open models, fastest, the universal fallback).
    ModelProfile("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B (Groq)",
                 reasoning=3, vision=False, context_window=128_000,
                 cost_tier="cheap", latency_tier="fast",
                 serves=("reason", "fast")),
    ModelProfile("groq", "meta-llama/llama-4-scout-17b-16e-instruct",
                 "Llama 4 Scout Vision (Groq)",
                 reasoning=2, vision=True, context_window=128_000,
                 cost_tier="cheap", latency_tier="fast",
                 serves=("vision",)),
    # ---- Local (Ollama) — private, on-device, zero cost, variable strength.
    ModelProfile("ollama", "llama3.1", "Llama 3.1 (Local)",
                 reasoning=2, vision=False, context_window=128_000,
                 cost_tier="free", latency_tier="slow",
                 serves=("reason", "fast")),
    ModelProfile("ollama", "llava", "LLaVA Vision (Local)",
                 reasoning=2, vision=True, context_window=32_000,
                 cost_tier="free", latency_tier="slow",
                 serves=("vision",)),
]

# Provider display metadata for the picker (the "brand" of the brain).
PROVIDER_LABELS = {
    "anthropic": "Claude",
    "openai": "GPT",
    "gemini": "Gemini",
    "groq": "Groq",
    "ollama": "Local",
}


def profiles_for(provider: str) -> list[ModelProfile]:
    return [p for p in CATALOG if p.provider == provider]


def best_for_tier(provider: str, tier: str) -> Optional[ModelProfile]:
    """The strongest model a provider offers for a tier: highest reasoning
    for reason, fastest for fast, best vision reasoner for vision."""
    candidates = [p for p in profiles_for(provider) if tier in p.serves]
    if not candidates:
        return None
    if tier == "fast":
        # Prefer cheap+fast; break ties by reasoning.
        return sorted(candidates, key=lambda p: (_latency_rank(p.latency_tier),
                                                  -p.reasoning))[0]
    # reason / vision: strongest reasoner wins.
    return sorted(candidates, key=lambda p: (-p.reasoning,
                                             _latency_rank(p.latency_tier)))[0]


def profile(provider: str, model: str) -> Optional[ModelProfile]:
    return next((p for p in CATALOG if p.provider == provider and p.model == model), None)


# Auto-routing preference: which providers to try, strongest-planner first.
# The router intersects this with what is actually available (real keys).
AUTO_PROVIDER_PRIORITY = ("anthropic", "openai", "gemini", "groq", "ollama")


def _latency_rank(tier: str) -> int:
    return {"fast": 0, "medium": 1, "slow": 2}.get(tier, 1)
