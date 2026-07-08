"""Run a PerceptAI runner: `python -m runner` (or `perceptai-runner`).

  perceptai-runner --doctor    verify this host is ready — run this FIRST
  perceptai-runner             start working the queue (runs the same checks
                               first and refuses to start on a broken host)

Executing takes over the real mouse/keyboard on THIS machine — run it on a host
dedicated to automation. Credentials come from registering a runner in the
dashboard (/dashboard/runners).
"""
from __future__ import annotations

import os
import signal
import sys

from .config import RunnerConfig
from .doctor import DoctorReport, format_report, run_doctor, terminal_supports_unicode
from .worker import Worker

_ENV_KEYS = ("RUNNER_PLANE_URL", "RUNNER_TOKEN", "RUNNER_SIGNING_KEY")


def _raw_env() -> dict[str, str]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return {k: os.getenv(k, "") for k in _ENV_KEYS}


def _config_or_none(raw: dict[str, str]):
    if all(raw.get(k) for k in _ENV_KEYS):
        return RunnerConfig(plane_url=raw["RUNNER_PLANE_URL"].rstrip("/"),
                            token=raw["RUNNER_TOKEN"], signing_key=raw["RUNNER_SIGNING_KEY"])
    return None


def _diagnose(raw: dict[str, str]):
    """Build a config + client if possible, then run the full readiness report."""
    from .client import HttpControlPlane
    config = _config_or_none(raw)
    client = HttpControlPlane(config) if config is not None else None
    return config, client, run_doctor(config, raw, client=client)


def _print_report(report: DoctorReport) -> None:
    # Adapt to the terminal: color only on a TTY, ASCII glyphs when the console
    # (e.g. Windows cp1252) can't encode ✓/✗.
    print(format_report(report, color=sys.stdout.isatty(),
                        unicode=terminal_supports_unicode()))


def _doctor() -> int:
    _, _, report = _diagnose(_raw_env())
    _print_report(report)
    return 0 if report.ready else 1


def _serve() -> int:
    raw = _raw_env()
    config, client, report = _diagnose(raw)
    if not report.ready or config is None or client is None:
        _print_report(report)
        print("Refusing to start on a host that isn't ready. Fix the issues above "
              "and re-run `perceptai-runner --doctor`.", flush=True)
        return 1
    if report.warnings:
        _print_report(report)

    from .control import RemoteControlChannel
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
    return 0


def main() -> None:
    if "--doctor" in sys.argv[1:]:
        sys.exit(_doctor())
    sys.exit(_serve())


if __name__ == "__main__":
    main()
