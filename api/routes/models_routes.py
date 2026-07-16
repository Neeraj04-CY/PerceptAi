"""Models route: the honest, real model picker.

Returns exactly the providers this deployment can actually use (a real key
is present) plus the full capability catalog, so the UI shows latency,
cost, reasoning strength, vision and context window per model — never a
fake dropdown. `available: false` providers are listed too, with WHY, so
an operator knows what to configure to unlock them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import get_current_user

router = APIRouter(prefix="/models", tags=["models"])

_HOW_TO_ENABLE = {
    "anthropic": "Set ANTHROPIC_API_KEY",
    "openai": "Set OPENAI_API_KEY",
    "gemini": "Set GEMINI_API_KEY (or GOOGLE_API_KEY)",
    "groq": "Set GROQ_API_KEY",
    "ollama": "Set OLLAMA_HOST (e.g. http://localhost:11434) and run Ollama",
}
# The value string the /execute request should send for each provider.
_PICKER_VALUE = {"anthropic": "claude", "openai": "gpt", "gemini": "gemini",
                 "groq": "groq", "ollama": "local"}


@router.get("")
async def list_models(current_user: dict = Depends(get_current_user)):
    from perceptai import model_catalog as mc
    from perceptai.llm import LLMClient

    # A cheap probe of what is configured on this host (no model calls).
    try:
        from executor import _engine_config, _load_engine  # type: ignore
        AgentSession, EngineConfig, *_ = _load_engine()
        client = LLMClient(_engine_config(EngineConfig)) if EngineConfig else None
        available = set(client.available_providers()) if client else set()
        active = client.active_provider() if client else ""
    except Exception:
        available, active = set(), ""

    providers = []
    for name in mc.AUTO_PROVIDER_PRIORITY:
        models = [p.to_dict() for p in mc.profiles_for(name)]
        if not models:
            continue
        providers.append({
            "provider": name,
            "label": mc.PROVIDER_LABELS.get(name, name.title()),
            "picker_value": _PICKER_VALUE.get(name, name),
            "available": name in available,
            "how_to_enable": None if name in available else _HOW_TO_ENABLE.get(name),
            "is_active_auto": name == active,
            "models": models,
        })

    return {
        "active_provider": active,
        "any_frontier": bool(available & {"anthropic", "openai", "gemini"}),
        "providers": providers,
    }
