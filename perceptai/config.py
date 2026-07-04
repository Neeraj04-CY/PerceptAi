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

    # Models
    planner_model: str = "llama-3.3-70b-versatile"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Budgets — every agentic loop is bounded
    max_steps: int = 12
    max_plan_steps: int = 5
    max_healing_attempts: int = 2
    max_replans: int = 4
    find_retries: int = 3
    healing_confidence_threshold: float = 0.5

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

    # Perception
    fast_cache_ttl_s: float = 0.8
    ocr_max_side: int = 960
    screenshot_keep: int = 5

    # World model — providers
    uia_enabled: bool = True
    uia_max_elements: int = 120       # cap on UIA tree nodes per snapshot
    uia_max_depth: int = 12
    uia_time_budget_s: float = 1.5    # hard wall-clock budget for the tree walk
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

    # Settle delays (seconds)
    settle_after_launch_s: float = 2.5
    settle_after_step_s: float = 0.2
    settle_before_input_s: float = 0.2
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
        return cls(groq_api_key=os.getenv("GROQ_API_KEY", ""), **overrides)
