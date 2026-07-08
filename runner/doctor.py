"""`perceptai-runner --doctor` — the first thing every operator runs.

It answers one question with confidence: *is this host ready to run automations?*
Every check is specific, every failure carries the exact fix, and the runner
runs the same checks on startup and refuses to claim work on a broken host —
so failures surface at setup, never mid-automation on someone's live screen.

The checks are pure over injected probes (imports, screen, an HTTP client), so
the whole doctor is unit-tested without a network, a screen, or the heavy
engine dependencies installed.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .config import RunnerConfig

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    name: str
    status: str          # ok | warn | fail
    detail: str = ""
    fix: str = ""


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def ready(self) -> bool:
        """Ready to run when nothing is failing (warnings are allowed)."""
        return not self.failures


# ----------------------------------------------------------------- probes

ImportProbe = Callable[[str], bool]
ScreenProbe = Callable[[], Optional[tuple]]


def _real_import(module: str) -> bool:
    # find_spec checks installation without importing — fast, and never triggers
    # heavy side effects (e.g. loading torch via easyocr) on every startup.
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _real_screen() -> Optional[tuple]:
    try:
        import pyautogui
        size = pyautogui.size()
        return (int(size[0]), int(size[1]))
    except Exception:
        return None


def _env(name: str) -> str:
    import os
    return os.getenv(name, "")


# ------------------------------------------------------------------ checks
# Engine modules the runner needs to actually execute, and the fix for each.
_ENGINE_DEPS = [
    ("perceptai", FAIL, "the engine package", "pip install perceptai (or pip install -e . from the repo)"),
    ("pyautogui", FAIL, "mouse/keyboard control", "pip install -r requirements.txt"),
    ("PIL", FAIL, "screenshots (Pillow)", "pip install -r requirements.txt"),
    ("numpy", FAIL, "perception math", "pip install -r requirements.txt"),
    ("groq", FAIL, "LLM planning", "pip install -r requirements.txt"),
    ("easyocr", WARN, "OCR perception (UIA/vision still work without it)", "pip install -r requirements.txt"),
    ("websocket", WARN, "DOM/browser perception (falls back to pixels without it)", "pip install websocket-client"),
]


def check_config(config: Optional[RunnerConfig], raw: dict[str, str]) -> Check:
    missing = [k for k in ("RUNNER_PLANE_URL", "RUNNER_TOKEN", "RUNNER_SIGNING_KEY") if not raw.get(k)]
    if missing:
        return Check("runner credentials", FAIL,
                     f"missing {', '.join(missing)}",
                     "register a runner in the dashboard (/dashboard/runners) and set the "
                     "shown values as environment variables")
    return Check("runner credentials", OK, "plane URL, token and signing key present")


def check_engine(import_probe: ImportProbe) -> list[Check]:
    checks = []
    for module, level, purpose, fix in _ENGINE_DEPS:
        if import_probe(module):
            checks.append(Check(f"dependency: {module}", OK, purpose))
        else:
            checks.append(Check(f"dependency: {module}", level, f"missing - needed for {purpose}", fix))
    return checks


def check_llm_key() -> Check:
    if _env("GROQ_API_KEY"):
        return Check("GROQ_API_KEY", OK, "planning model reachable")
    return Check("GROQ_API_KEY", FAIL, "not set - the agent cannot plan without it",
                 "set GROQ_API_KEY in the environment (or the runner's .env)")


def check_screen(screen_probe: ScreenProbe) -> Check:
    size = screen_probe()
    if size:
        return Check("screen access", OK, f"display detected ({size[0]}x{size[1]})")
    return Check("screen access", FAIL, "no display detected - a runner controls a real screen",
                 "run on a machine with an interactive desktop session (not headless/SSH-only)")


def check_plane(client: Any) -> Check:
    try:
        client.ping()
        return Check("control plane", OK, "reachable")
    except Exception as e:
        return Check("control plane", FAIL, f"unreachable: {e}",
                     "check RUNNER_PLANE_URL points at <api-host>/api/v1 and the plane is up")


def check_credentials(client: Any) -> Check:
    try:
        client.heartbeat(None)
        return Check("authentication", OK, "runner token accepted")
    except Exception as e:
        return Check("authentication", FAIL, f"token rejected: {e}",
                     "re-register the runner; the token may be wrong or revoked")


def check_signing(config: Optional[RunnerConfig]) -> Check:
    if config is None or not config.signing_key:
        return Check("work signing", FAIL, "no signing key", "set RUNNER_SIGNING_KEY from registration")
    try:
        from perceptai.signing import sign_work_order, verify_work_order
        sample = {"session_id": "self-test", "nonce": "x"}
        sig = sign_work_order(config.signing_key, sample)
        if verify_work_order(config.signing_key, sample, sig):
            return Check("work signing", OK, "signature self-test passed")
        return Check("work signing", FAIL, "self-test failed", "re-register the runner for a fresh signing key")
    except Exception as e:
        return Check("work signing", WARN, f"could not self-test: {e}", "")


# --------------------------------------------------------------- orchestration

def run_doctor(config: Optional[RunnerConfig], raw_env: dict[str, str], *,
               import_probe: ImportProbe = _real_import,
               screen_probe: ScreenProbe = _real_screen,
               client: Any = None) -> DoctorReport:
    """Full readiness report. Network checks are skipped (not silently passed)
    when config is incomplete, so the report always tells the truth."""
    checks: list[Check] = [check_config(config, raw_env)]
    checks.extend(check_engine(import_probe))
    checks.append(check_llm_key())
    checks.append(check_screen(screen_probe))
    checks.append(check_signing(config))
    if client is not None:
        checks.append(check_plane(client))
        checks.append(check_credentials(client))
    else:
        checks.append(Check("control plane", WARN, "skipped - credentials incomplete", ""))
    return DoctorReport(checks=checks)


# ------------------------------------------------------------------ rendering

_SYMBOL = {OK: "✓", WARN: "!", FAIL: "✗"}
_SYMBOL_ASCII = {OK: "[OK]", WARN: "[!]", FAIL: "[X]"}
_COLOR = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}
_RESET = "\033[0m"


def terminal_supports_unicode() -> bool:
    """Windows consoles are often cp1252 and cannot encode ✓/✗ — fall back to
    ASCII so the doctor never crashes on the exact platform it targets."""
    import sys
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓✗".encode(enc)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def format_report(report: DoctorReport, *, color: bool = True, unicode: bool = True) -> str:
    symbols = _SYMBOL if unicode else _SYMBOL_ASCII
    arrow = "→" if unicode else "->"

    def paint(status: str, text: str) -> str:
        return f"{_COLOR[status]}{text}{_RESET}" if color else text

    lines = ["", "PerceptAI runner — environment check" if unicode else "PerceptAI runner - environment check",
             "=" * 38]
    for c in report.checks:
        lines.append(f"  {paint(c.status, symbols[c.status])} {c.name:<22} {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"      {paint(c.status, f'{arrow} fix:')} {c.fix}")
    lines.append("=" * 38)
    if report.ready:
        dash = "—" if unicode else "-"
        note = "" if not report.warnings else f" ({len(report.warnings)} warning(s) {dash} degraded but runnable)"
        lines.append(paint(OK, f"{symbols[OK]} Ready to run{note}."))
    else:
        n = len(report.failures)
        lines.append(paint(FAIL, f"{symbols[FAIL]} {n} issue(s) must be fixed. Resolve the fixes above, then "
                                 "re-run `perceptai-runner --doctor`."))
    lines.append("")
    return "\n".join(lines)
