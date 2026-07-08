"""Sprint 5 Step 1 — `--doctor` readiness checks. Pure over injected probes:
no network, no screen, no heavy engine deps installed. Proves every failure is
specific and carries a fix, and that a broken host is reported as not-ready."""
from __future__ import annotations

from runner.config import RunnerConfig
from runner.doctor import FAIL, OK, format_report, run_doctor

RAW_OK = {"RUNNER_PLANE_URL": "http://x/api/v1", "RUNNER_TOKEN": "rk_t", "RUNNER_SIGNING_KEY": "key"}
CONFIG = RunnerConfig(plane_url="http://x/api/v1", token="rk_t", signing_key="key")

ALL_INSTALLED = lambda _m: True          # noqa: E731
SCREEN = lambda: (1920, 1080)            # noqa: E731
NO_SCREEN = lambda: None                 # noqa: E731


class GoodClient:
    def ping(self): pass
    def heartbeat(self, sid): pass


def _find(report, name):
    return next(c for c in report.checks if c.name == name)


def test_all_ready(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    report = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED,
                        screen_probe=SCREEN, client=GoodClient())
    assert report.ready and not report.failures
    assert _find(report, "work signing").status == OK
    assert "Ready to run" in format_report(report, color=False)


def test_missing_credentials_fails_and_skips_network(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    raw = {"RUNNER_PLANE_URL": "", "RUNNER_TOKEN": "", "RUNNER_SIGNING_KEY": ""}
    report = run_doctor(None, raw, import_probe=ALL_INSTALLED, screen_probe=SCREEN, client=None)
    cred = _find(report, "runner credentials")
    assert cred.status == FAIL and "dashboard" in cred.fix
    # network checks are skipped honestly, not silently passed
    assert _find(report, "control plane").status != OK
    assert not report.ready


def test_missing_engine_dependency(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    probe = lambda m: m != "pyautogui"  # noqa: E731
    report = run_doctor(CONFIG, RAW_OK, import_probe=probe, screen_probe=SCREEN, client=GoodClient())
    dep = _find(report, "dependency: pyautogui")
    assert dep.status == FAIL and "requirements.txt" in dep.fix
    assert not report.ready


def test_missing_ocr_is_warning_not_failure(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    probe = lambda m: m != "easyocr"  # noqa: E731
    report = run_doctor(CONFIG, RAW_OK, import_probe=probe, screen_probe=SCREEN, client=GoodClient())
    assert _find(report, "dependency: easyocr").status == "warn"
    assert report.ready  # degraded but runnable


def test_missing_llm_key_fails(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    report = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED, screen_probe=SCREEN, client=GoodClient())
    assert _find(report, "GROQ_API_KEY").status == FAIL
    assert not report.ready


def test_no_screen_fails(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    report = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED, screen_probe=NO_SCREEN, client=GoodClient())
    scr = _find(report, "screen access")
    assert scr.status == FAIL and "headless" in scr.fix
    assert not report.ready


def test_plane_unreachable_and_bad_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    class BadPing(GoodClient):
        def ping(self): raise ConnectionError("connection refused")
    r1 = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED, screen_probe=SCREEN, client=BadPing())
    assert _find(r1, "control plane").status == FAIL

    class BadAuth(GoodClient):
        def heartbeat(self, sid): raise Exception("401 Unauthorized")
    r2 = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED, screen_probe=SCREEN, client=BadAuth())
    auth = _find(r2, "authentication")
    assert auth.status == FAIL and "re-register" in auth.fix


def test_format_report_renders_fixes_and_verdict(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    report = run_doctor(CONFIG, RAW_OK, import_probe=ALL_INSTALLED, screen_probe=NO_SCREEN, client=GoodClient())
    text = format_report(report, color=False)
    assert "→ fix:" in text
    assert "must be fixed" in text
    assert "✗" in text and "✓" in text  # both failing and passing checks shown
