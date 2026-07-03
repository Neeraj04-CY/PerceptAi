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

    # Perception
    fast_cache_ttl_s: float = 0.8
    ocr_max_side: int = 960
    screenshot_keep: int = 5

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
