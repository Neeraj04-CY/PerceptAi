"""Engine configuration. Every tunable lives here; nothing is hardcoded
inside the runtime. The timing values are load-bearing settle delays for
real UI interaction — tune, don't delete.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _default_workspace_root() -> Path:
    return Path(tempfile.gettempdir()) / "perceptai"


def _default_memory_db() -> Path:
    return Path.home() / ".perceptai" / "memory.db"


@dataclass
class EngineConfig:
    groq_api_key: str = ""
    anthropic_api_key: str = ""   # frontier brain (Claude); when set, it leads
    openai_api_key: str = ""      # GPT (also Azure OpenAI)
    gemini_api_key: str = ""      # Google Gemini
    ollama_host: str = ""         # local models, e.g. http://localhost:11434

    # Model orchestration (Chapter XV, multi-provider). Roles route to a tier;
    # a tier maps to a provider+model chosen by CAPABILITY from model_catalog.
    # `auto` walks the priority (strongest planner first) and takes the first
    # provider that is actually configured; legacy Groq behavior is preserved
    # exactly when only Groq is available — zero regression.
    model_provider: str = "auto"  # auto | anthropic | openai | gemini | groq | ollama
    # Groq path (legacy / universal fallback)
    planner_model: str = "llama-3.3-70b-versatile"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # Frontier path — the most capable models handle hard reasoning + grounding;
    # a fast model handles mechanical extraction. Overridable for bring-your-own.
    anthropic_reason_model: str = "claude-sonnet-5"
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"
    anthropic_vision_model: str = "claude-sonnet-5"
    reason_model: str = ""        # explicit per-run reasoner pin (any provider)

    # Budgets — every agentic loop is bounded
    max_steps: int = 12
    max_plan_steps: int = 5
    max_healing_attempts: int = 2
    max_replans: int = 4
    find_retries: int = 3
    # The initial plan gates the whole mission — a single empty/malformed
    # reply from the planning model kills the run before it starts. Retry
    # it a few times against transient variance (each attempt is one cheap
    # LLM call). The frontier model rarely needs this; the Groq fallback
    # benefits materially.
    initial_plan_attempts: int = 3
    healing_confidence_threshold: float = 0.5

    # The Plan Critic (Chapter XVI) — verification BEFORE action.
    critic_enabled: bool = True
    critic_min_score: float = 0.6         # below this, the plan is rejected
    critic_ambiguity_margin: float = 0.15  # top-2 match gap under this = AMBIGUOUS
    critic_weak_grounding: float = 0.75    # best match under this is weak
    critic_max_revisions: int = 2          # planner<->critic convergence budget
    critic_llm_enabled: bool = True        # adversarial pass, escalated only when it pays
    critic_escalate_below: float = 0.85    # ...or when a high-risk step is present

    # Reasoning — budgets for the decision loop and the thresholds that
    # turn uncertainty into behavior (observe more, verify more, escalate).
    max_cycles: int = 80                  # absolute bound on reasoning cycles per run
    max_recovery_total: int = 6           # recovery attempts per run (max_healing_attempts is per failure)
    max_llm_calls: int = 60
    max_vision_escalations: int = 3
    max_task_duration_s: float = 600.0
    low_confidence_threshold: float = 0.55  # world confidence below this is an uncertainty signal
    ambiguity_similarity: float = 0.75      # element-label similarity that reads as confusable
    slow_provider_ms: float = 8000.0        # provider latency that suggests a busy/loading app
    blocked_window_titles: list = field(default_factory=list)  # policy: never send input to these

    # Trust layer (Sprint 3) — control checkpoint + risk-gated approval.
    # Risk *observation* is always on (pure observability, emitted per step).
    # Risk *gating* is off by default: a run behaves exactly as before unless
    # a workspace policy sets an approval threshold. Budgets bound every wait
    # so a paused or approval-blocked run can never hang the host.
    risk_detection_enabled: bool = True
    approval_risk_threshold: str = ""       # "" (off) | "low" | "medium" | "high": gate at/above this level
    max_pause_s: float = 900.0              # a paused run resumes or is stopped within this budget
    max_approval_wait_s: float = 600.0      # an unanswered approval denies (honest) after this budget
    control_poll_s: float = 0.25            # cadence the checkpoint re-reads control state while parked

    # Perception
    fast_cache_ttl_s: float = 0.8
    ocr_max_side: int = 960
    screenshot_keep: int = 5
    # Adaptive perception: skip OCR on a snapshot when the structured
    # sources (UIA/DOM) already produced enough elements. Measured on real
    # runs: OCR cost ~7s/snapshot while UIA grounded the same click at 0.99
    # in ~170ms. Pixels stay the floor — a find-miss retries WITH OCR, and
    # read_screen always includes it (text_critical).
    adaptive_perception: bool = True
    ocr_skip_min_elements: int = 12

    # World model — providers
    uia_enabled: bool = True
    uia_max_elements: int = 120       # cap on UIA tree nodes per snapshot
    uia_max_depth: int = 12
    uia_time_budget_s: float = 1.5    # hard wall-clock budget for the tree walk

    # Browser/DOM provider (Sprint 6) — structural fidelity on the web via the
    # Chrome DevTools Protocol. Pixels stay the floor: when no debuggable
    # Chromium is present the provider contributes nothing and OCR/UIA carry.
    dom_enabled: bool = True
    dom_host: str = "127.0.0.1"
    dom_debug_port: int = 9222        # CDP endpoint the provider attaches to
    dom_max_elements: int = 150       # cap on AX nodes emitted per snapshot
    dom_time_budget_s: float = 1.5    # hard wall-clock budget for a CDP read
    # When the engine launches a browser, start it debuggable so the DOM
    # provider can attach. Real-screen behavior — validated by perception_bench.
    browser_debug_launch: bool = True
    # Base trust per observation source; observation confidence is
    # provider-native score × source trust. Confidence is never faked:
    # a source that guesses (vision) can never outrank one that knows (uia).
    source_trust: dict = field(default_factory=lambda: {
        "os": 0.99, "uia": 0.95, "dom": 0.98, "accessibility": 0.9,
        "clipboard": 0.9, "ocr": 0.75, "vision": 0.6, "memory": 0.5,
        "custom": 0.5,
    })

    # World model — fusion
    fusion_iou_threshold: float = 0.35     # spatial overlap that means "same element"
    fusion_text_similarity: float = 0.82   # fuzzy text match that means "same element"
    world_max_elements: int = 200          # hard cap on fused elements per snapshot
    describe_max_elements: int = 40        # elements listed in the planner view
    describe_max_chars: int = 4000         # char budget of the planner view

    # Settle delays (seconds). Load-bearing for real UI — tune, don't delete.
    settle_after_launch_s: float = 2.5
    settle_after_step_s: float = 0.2
    settle_before_input_s: float = 0.2
    settle_before_read_s: float = 1.0      # let the screen finish rendering before READ_SCREEN
    find_retry_wait_s: float = 1.0         # wait before re-observing when an element isn't found yet
    recovery_retry_wait_s: float = 1.0     # backoff between recovery attempts
    # Reliability (Sprint 5): after a recovery action (dismiss dialog, refocus…)
    # let the screen settle BEFORE measuring whether the failure cleared —
    # otherwise recovery is judged on a half-rendered screen and falsely fails.
    # Real-screen heuristic: the value is validated by the eval suite, not here.
    settle_after_recovery_s: float = 0.5
    window_appear_timeout_s: float = 10.0

    # Paths
    workspace_root: Path = field(default_factory=_default_workspace_root)
    memory_db_path: Path = field(default_factory=_default_memory_db)

    # Environment
    preferred_browser: str = ""  # empty = system default browser

    @classmethod
    def from_env(cls, **overrides) -> "EngineConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        env = {
            "groq_api_key": os.getenv("GROQ_API_KEY", ""),
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "gemini_api_key": os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""),
            "ollama_host": os.getenv("OLLAMA_HOST", ""),
        }
        if os.getenv("MODEL_PROVIDER"):
            env["model_provider"] = os.getenv("MODEL_PROVIDER", "auto")
        env.update(overrides)
        return cls(**env)
