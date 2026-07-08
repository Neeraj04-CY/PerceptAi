"""Run a PerceptAI runner: `python -m runner`.

Reads RUNNER_PLANE_URL / RUNNER_TOKEN / RUNNER_SIGNING_KEY (from the runner
registration) and works the queue until interrupted. Executing takes over the
real mouse/keyboard on THIS machine — run it on a host dedicated to automation.
"""
from __future__ import annotations

import signal
import sys

from .client import HttpControlPlane
from .config import RunnerConfig
from .control import RemoteControlChannel
from .worker import Worker


def main() -> None:
    config = RunnerConfig.from_env()
    client = HttpControlPlane(config)
    # Honor operator control (pause/resume/stop/approval) over the network.
    worker = Worker(client, config,
                    control_factory=lambda sid: RemoteControlChannel(client, sid))

    def _shutdown(*_):
        print("\nRunner shutting down…", flush=True)
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print(f"Runner online — plane {config.plane_url}, polling for work.", flush=True)
    worker.run_forever()


if __name__ == "__main__":
    main()
