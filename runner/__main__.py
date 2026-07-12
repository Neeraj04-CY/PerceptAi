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
from .identity import RunnerIdentity
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
    # RUNNER_SIGNING_KEY is the LEGACY symmetric credential. It is optional: a
    # runner with a cryptographic identity verifies work orders with the plane's
    # public key and holds no secret capable of forging one.
    if all(raw.get(k) for k in ("RUNNER_PLANE_URL", "RUNNER_TOKEN")):
        return RunnerConfig(plane_url=raw["RUNNER_PLANE_URL"].rstrip("/"),
                            token=raw["RUNNER_TOKEN"],
                            signing_key=raw.get("RUNNER_SIGNING_KEY", ""))
    return None


def _diagnose(raw: dict[str, str]):
    """Build a config + identity + client if possible, then run the full report."""
    from .client import HttpControlPlane
    config = _config_or_none(raw)
    identity = RunnerIdentity.load_or_create() if config is not None else None
    client = HttpControlPlane(config, identity) if config is not None else None
    return config, identity, client, run_doctor(config, raw, identity=identity, client=client)


def _ensure_enrolled(client, identity: RunnerIdentity) -> bool:
    """Publish our public key once (trust on first use) and learn the plane's.

    Idempotent from the runner's side: an already-enrolled runner keeps its
    stored plane key and carries on. A 409 means the plane already holds a key
    for this runner — if it is not ours, that is an incident, and the runner
    refuses to run rather than silently failing every signature.
    """
    if identity.enrolled and identity.plane_public_key:
        return True
    try:
        result = client.enroll(identity.public_key)
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 409:
            print("This runner already enrolled a DIFFERENT key with the control "
                  "plane. Re-register the runner in the dashboard to rotate its "
                  "identity, then start it again.", flush=True)
            return False
        print(f"Could not enroll this runner's identity with the plane: {e}", flush=True)
        return False
    identity.plane_public_key = result.get("plane_public_key", "")
    identity.enrolled = True
    identity.save()
    return bool(identity.plane_public_key)


def _print_report(report: DoctorReport) -> None:
    # Adapt to the terminal: color only on a TTY, ASCII glyphs when the console
    # (e.g. Windows cp1252) can't encode ✓/✗.
    print(format_report(report, color=sys.stdout.isatty(),
                        unicode=terminal_supports_unicode()))


def _doctor() -> int:
    _, _, _, report = _diagnose(_raw_env())
    _print_report(report)
    return 0 if report.ready else 1


def _serve() -> int:
    raw = _raw_env()
    config, identity, client, report = _diagnose(raw)
    if not report.ready or config is None or client is None or identity is None:
        _print_report(report)
        print("Refusing to start on a host that isn't ready. Fix the issues above "
              "and re-run `perceptai-runner --doctor`.", flush=True)
        return 1
    if report.warnings:
        _print_report(report)

    # Cryptographic identity before any work is claimed: the private key stays
    # on this machine, the plane's public key lets us verify what it sends.
    if not _ensure_enrolled(client, identity):
        return 1

    from .control import RemoteControlChannel
    from .secrets import RemoteSecretResolver
    worker = Worker(
        client, config, identity=identity,
        control_factory=lambda sid: RemoteControlChannel(client, sid),
        secrets_factory=lambda sid, order: RemoteSecretResolver(
            client, sid, order.get("available_secrets", [])),
    )

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
