"""Runner configuration. Every tunable is here; nothing is hardcoded in the
work loop. Budgets bound every loop (poll backoff, heartbeat, event flush) so
a runner never spins hot or hangs."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RunnerConfig:
    plane_url: str          # control-plane base, e.g. https://host/api/v1
    token: str              # runner token (rk_*), bootstrap credential
    # LEGACY symmetric key to verify signed work orders. Optional: an enrolled
    # runner verifies with the plane's public key and holds no forgeable secret.
    signing_key: str = ""

    # Claim long-poll: idle backoff between empty claims (bounded).
    poll_interval_s: float = 2.0
    poll_max_interval_s: float = 15.0
    # Liveness + lease renewal cadence (well inside the plane's lease window).
    heartbeat_interval_s: float = 30.0
    # Live-relay latency vs chattiness: flush events every window or when a
    # batch fills, whichever comes first.
    event_flush_interval_s: float = 0.25
    event_batch_max: int = 50
    request_timeout_s: float = 30.0
    # Reconnect backoff when the plane is unreachable (bounded).
    reconnect_max_s: float = 30.0
    # How often an unready host (locked, logged out, no screen) re-checks
    # whether it can execute again. Bounded: an unready runner is cheap.
    readiness_recheck_s: float = 15.0
    # Mid-run session truth: the engine hits its control checkpoint many times
    # per cycle, so the (Win32 + display) probe is cached for this long. Small
    # enough that a lock is caught within seconds; large enough to stay free.
    readiness_probe_interval_s: float = 2.0

    @classmethod
    def from_env(cls) -> "RunnerConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        plane = os.getenv("RUNNER_PLANE_URL", "").rstrip("/")
        token = os.getenv("RUNNER_TOKEN", "")
        key = os.getenv("RUNNER_SIGNING_KEY", "")   # legacy, optional
        if not (plane and token):
            raise SystemExit(
                "Runner needs RUNNER_PLANE_URL and RUNNER_TOKEN (from the runner "
                "registration). Set them in the environment or .env."
            )
        return cls(plane_url=plane, token=token, signing_key=key)
