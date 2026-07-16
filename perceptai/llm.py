"""Model Orchestration — the ONE model access point for the engine.

WHY THIS EXISTS (Chapter XV). A screen-automation agent is only as capable as
the model that plans and grounds its actions. The engine was capped at a single
open 70B model; competitors' whole ceiling IS their frontier model. This layer
uncaps and orchestrates the brain:

  * PROVIDER-AGNOSTIC. Anthropic (Claude), Groq, and any future provider sit
    behind one `ModelProvider` interface. An enterprise runs the platform with
    THEIR sanctioned model (Bedrock Claude, Azure OpenAI) — something Operator
    and Copilot Studio cannot offer.
  * ROLE-ROUTED. Each cognitive task is a ROLE (plan / ground / heal / verify /
    judge / extract / report / perceive). Hard reasoning and grounding route to
    the frontier model; mechanical extraction routes to a fast one. One 70B for
    everything was leaving both capability and cost on the table.
  * FRONTIER-FIRST, DEGRADE-SAFE. When an Anthropic key is present the reasoning
    and vision roles use Claude; otherwise the layer behaves EXACTLY as before
    (Groq). A provider failure falls back to the fast provider. A malformed
    reply degrades to (None, raw) — never an exception in the execution path.

Still the single data-egress checkpoint (Chapter IX): every outbound prompt and
screenshot passes the injected `EgressGuard` before it can reach any provider.
There is nowhere else to call a model from.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from .egress import NULL_GUARD, EgressGuard

# ------------------------------------------------------------------- roles
# A role is WHAT the model is being asked to do, not WHICH model does it.
PLAN = "plan"          # decide the next steps from the live screen (hard)
GROUND = "ground"      # locate an element (hard, vision-heavy)
HEAL = "heal"          # diagnose a failure and propose recovery (hard)
VERIFY = "verify"      # judge whether the outcome was achieved (hard)
GOAL = "goal"          # turn the instruction into a GoalSpec (hard)
JUDGE = "judge"        # workforce/mission-level judgement (hard)
CRITIC = "critic"      # attack the plan before it runs (hard, adversarial)
EXTRACT = "extract"    # pull typed values out of observed text (mechanical)
REPORT = "report"      # compose the narrative from evidence (mechanical)
PERCEIVE = "perceive"  # vision understanding of a screenshot (vision)

# Which roles want the frontier reasoner, the fast model, or the vision model.
_REASON_ROLES = frozenset({PLAN, GROUND, HEAL, VERIFY, GOAL, JUDGE, CRITIC})
_FAST_ROLES = frozenset({EXTRACT, REPORT})
_VISION_ROLES = frozenset({PERCEIVE})

REASON, FAST, VISION = "reason", "fast", "vision"


def _tier(role: str) -> str:
    if role in _VISION_ROLES:
        return VISION
    if role in _FAST_ROLES:
        return FAST
    return REASON  # unknown roles get the capable model — never silently cheap


def parse_json_reply(raw: str) -> Optional[Any]:
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


@dataclass(frozen=True)
class ModelSpec:
    provider: str        # "anthropic" | "groq"
    model: str
    max_tokens: int


# ============================================================== providers

class ModelProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str: ...
    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str: ...


class GroqProvider:
    """The original path — unchanged behavior, kept as the universal fallback."""
    name = "groq"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def available(self) -> bool:
        return bool(self._api_key)

    def _c(self):
        if self._client is None:
            from groq import Groq  # lazy
            self._client = Groq(api_key=self._api_key)
        return self._client

    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content.strip()

    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": prompt}]}])
        return r.choices[0].message.content.strip()


class AnthropicProvider:
    """Claude — the frontier planner/grounder. Strong at reading messy real
    enterprise screens and at coordinate/element grounding, which is exactly
    where a 70B open model runs out of road."""
    name = "anthropic"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import importlib.util
            return importlib.util.find_spec("anthropic") is not None
        except Exception:
            return False

    def _c(self):
        if self._client is None:
            import anthropic  # lazy
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return _anthropic_text(r)

    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/png", "data": image_b64}},
                {"type": "text", "text": prompt}]}])
        return _anthropic_text(r)


def _anthropic_text(response: Any) -> str:
    """Extract text from a Claude messages response, defensively."""
    try:
        parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return "".join(parts).strip()
    except Exception:
        return ""


class OpenAIProvider:
    """GPT — frontier planner/grounder via the OpenAI SDK (also serves
    Azure OpenAI when the SDK is pointed at an Azure deployment)."""
    name = "openai"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import importlib.util
            return importlib.util.find_spec("openai") is not None
        except Exception:
            return False

    def _c(self):
        if self._client is None:
            from openai import OpenAI  # lazy
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return (r.choices[0].message.content or "").strip()

    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str:
        r = self._c().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": prompt}]}])
        return (r.choices[0].message.content or "").strip()


class GeminiProvider:
    """Gemini — Google's frontier model, notable for a very large context
    window (useful for long, cluttered enterprise screens)."""
    name = "gemini"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import importlib.util
            return importlib.util.find_spec("google.generativeai") is not None
        except Exception:
            return False

    def _c(self):
        if self._client is None:
            import google.generativeai as genai  # lazy
            genai.configure(api_key=self._api_key)
            self._client = genai
        return self._client

    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str:
        genai = self._c()
        m = genai.GenerativeModel(model)
        r = m.generate_content(
            prompt, generation_config={"max_output_tokens": max_tokens})
        return (getattr(r, "text", "") or "").strip()

    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str:
        import base64
        genai = self._c()
        m = genai.GenerativeModel(model)
        r = m.generate_content(
            [{"mime_type": "image/png", "data": base64.b64decode(image_b64)}, prompt],
            generation_config={"max_output_tokens": max_tokens})
        return (getattr(r, "text", "") or "").strip()


class OllamaProvider:
    """Local models via an Ollama host — private, on-device, zero cost. The
    only provider that keeps every prompt and screenshot on the machine,
    which is what a security-sensitive enterprise needs."""
    name = "ollama"

    def __init__(self, host: str):
        self._host = (host or "").rstrip("/")

    def available(self) -> bool:
        if not self._host:
            return False
        try:
            import importlib.util
            if importlib.util.find_spec("requests") is None:
                return False
            import requests  # lazy
            requests.get(f"{self._host}/api/tags", timeout=1.5)
            return True
        except Exception:
            return False

    def complete_text(self, prompt: str, model: str, max_tokens: int) -> str:
        import requests
        r = requests.post(f"{self._host}/api/generate", timeout=120, json={
            "model": model, "prompt": prompt, "stream": False,
            "options": {"num_predict": max_tokens}})
        return str(r.json().get("response", "")).strip()

    def complete_vision(self, image_b64: str, prompt: str, model: str, max_tokens: int) -> str:
        import requests
        r = requests.post(f"{self._host}/api/generate", timeout=180, json={
            "model": model, "prompt": prompt, "images": [image_b64], "stream": False,
            "options": {"num_predict": max_tokens}})
        return str(r.json().get("response", "")).strip()


# ================================================================ router

class LLMClient:
    """The router. Accepts an EngineConfig (or, for back-compat, a bare Groq
    api-key string). Chooses provider + model per ROLE, gates every send at the
    egress checkpoint, and never raises into the execution path."""

    def __init__(self, config: Any = None, egress: Optional[EgressGuard] = None,
                 api_key: Optional[str] = None):
        # Back-compat: `LLMClient("groq-key")` still works.
        if isinstance(config, str):
            api_key, config = config, None
        self._config = config
        self.egress: EgressGuard = egress or NULL_GUARD
        self.calls = 0

        groq_key = api_key if api_key is not None else _cfg(config, "groq_api_key", "")
        self._providers: dict[str, ModelProvider] = {
            "groq": GroqProvider(groq_key),
            "anthropic": AnthropicProvider(_cfg(config, "anthropic_api_key", "")),
            "openai": OpenAIProvider(_cfg(config, "openai_api_key", "")),
            "gemini": GeminiProvider(_cfg(config, "gemini_api_key", "")),
            "ollama": OllamaProvider(_cfg(config, "ollama_host", "")),
        }
        self._routing = _build_routing(config, self._providers)

    def available_providers(self) -> list[str]:
        """Providers with a real, usable configuration right now — the honest
        set the picker may offer. Never a fake dropdown."""
        return [name for name, p in self._providers.items() if _safe_available(p)]

    def active_provider(self) -> str:
        """The provider auto/override actually routes reasoning to."""
        return self._routing[REASON].provider

    # ------------------------------------------------------------ routing
    def spec_for(self, role: str) -> ModelSpec:
        return self._routing.get(_tier(role), self._routing[FAST])

    def model_for(self, role: str) -> str:
        """The model that WILL handle this role — for the event stream and
        PlannerOutput, so the record shows which brain actually ran."""
        return self.spec_for(role).model

    def provider_for(self, role: str) -> str:
        return self.spec_for(role).provider

    def _run(self, spec: ModelSpec, fn) -> str:
        """Call `fn(provider, model)` on the chosen provider; on failure or
        unavailability, degrade to the fast provider, then to nothing. Never
        raises — a dead model must not take down a run."""
        order = [spec.provider]
        fallback = self._routing[FAST].provider
        if fallback != spec.provider:
            order.append(fallback)
        if "groq" not in order:
            order.append("groq")
        for name in order:
            provider = self._providers.get(name)
            if provider is None or not _safe_available(provider):
                continue
            model = spec.model if name == spec.provider else self._routing[FAST].model
            try:
                self.calls += 1
                return fn(provider, model)
            except Exception:
                continue  # try the next provider
        return ""  # everything failed — degrade honestly

    # ----------------------------------------------------------- completions
    def complete_text(self, prompt: str, role: str = PLAN, *,
                      model: Optional[str] = None, max_tokens: Optional[int] = None,
                      purpose: Optional[str] = None) -> str:
        spec = self._override(self.spec_for(role), model, max_tokens)
        # Egress gate BEFORE any provider is touched: a denied prompt never
        # leaves, a redacted one is what actually goes.
        prompt, _ = self.egress.text(prompt, model=spec.model, purpose=purpose or role)
        return self._run(spec, lambda p, m: p.complete_text(prompt, m, spec.max_tokens))

    def complete_json(self, prompt: str, role: str = PLAN, *,
                      model: Optional[str] = None, max_tokens: Optional[int] = None,
                      purpose: Optional[str] = None) -> tuple[Optional[Any], str]:
        raw = self.complete_text(prompt, role, model=model, max_tokens=max_tokens, purpose=purpose)
        return parse_json_reply(raw), raw

    def complete_vision_json(self, image_b64: str, prompt: str, role: str = PERCEIVE, *,
                             model: Optional[str] = None, max_tokens: Optional[int] = None,
                             purpose: Optional[str] = None) -> tuple[Optional[Any], str]:
        """Screenshots are the crown-jewel exposure. When egress policy forbids
        pixels this degrades to "no observation" — the local providers (UIA,
        OCR, DOM) carry the run and pixels stay the perception floor on-machine."""
        spec = self._override(self.spec_for(role), model, max_tokens)
        decision = self.egress.pixels(model=spec.model, purpose=purpose or role,
                                      size=len(image_b64 or ""))
        if not decision.allowed:
            return None, ""
        prompt, _ = self.egress.text(prompt, model=spec.model, purpose=purpose or role)
        raw = self._run(spec, lambda p, m: p.complete_vision(image_b64, prompt, m, spec.max_tokens))
        return parse_json_reply(raw), raw

    @staticmethod
    def _override(spec: ModelSpec, model: Optional[str], max_tokens: Optional[int]) -> ModelSpec:
        if model is None and max_tokens is None:
            return spec
        return ModelSpec(provider=spec.provider, model=model or spec.model,
                         max_tokens=max_tokens or spec.max_tokens)


# --------------------------------------------------------------- helpers

def _cfg(config: Any, attr: str, default: Any) -> Any:
    return getattr(config, attr, default) if config is not None else default


def _safe_available(provider: ModelProvider) -> bool:
    try:
        return provider.available()
    except Exception:
        return False


_TIER_TOKENS = {REASON: 1200, FAST: 800, VISION: 1500}


def _build_routing(config: Any, providers: dict[str, ModelProvider]) -> dict[str, ModelSpec]:
    """The routing table: tier -> ModelSpec, chosen by CAPABILITY.

    `model_provider` (auto | anthropic | openai | gemini | groq | ollama)
    picks the family; `auto` walks the catalog priority (strongest planner
    first) and takes the first provider actually available. Each tier then
    gets that provider's best-fit model from the catalog. A provider that
    can't serve a tier (e.g. Groq text-only for vision) falls back to the
    strongest available vision provider for that tier alone. Legacy Groq
    behavior is preserved exactly when only Groq is available.
    """
    from . import model_catalog as mc

    override = str(_cfg(config, "model_provider", "auto") or "auto").lower()
    available = [n for n in mc.AUTO_PROVIDER_PRIORITY if _safe_available(providers.get(n))]
    if not available:  # nothing usable — keep the legacy Groq shape (degrade honestly)
        available = ["groq"]

    if override != "auto" and override in providers and _safe_available(providers[override]):
        primary = override
    else:
        primary = available[0]

    # Per-role explicit model overrides still win (enterprise pins a model).
    reason_override = _cfg(config, "reason_model", "") or _cfg(config, "anthropic_reason_model", "") \
        if primary == "anthropic" else _cfg(config, "reason_model", "")
    routing: dict[str, ModelSpec] = {}
    for tier in (REASON, FAST, VISION):
        prof = mc.best_for_tier(primary, tier)
        if prof is None:
            # This provider can't serve the tier: borrow the strongest
            # available provider that can (vision is the usual case).
            for alt in available:
                prof = mc.best_for_tier(alt, tier)
                if prof is not None:
                    break
        if prof is None:  # truly nothing (shouldn't happen) — legacy Groq
            groq_reason = _cfg(config, "planner_model", "llama-3.3-70b-versatile")
            groq_vision = _cfg(config, "vision_model",
                               "meta-llama/llama-4-scout-17b-16e-instruct")
            routing[tier] = ModelSpec("groq",
                                      groq_vision if tier == VISION else groq_reason,
                                      _TIER_TOKENS[tier])
            continue
        routing[tier] = ModelSpec(prof.provider, prof.model, _TIER_TOKENS[tier])

    if reason_override:
        r = routing[REASON]
        routing[REASON] = ModelSpec(r.provider, reason_override, r.max_tokens)
    return routing
