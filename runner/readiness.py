"""Session truth — is THIS host actually able to drive a desktop right now?

The platform must never pretend work can execute when the execution
environment cannot. A locked workstation, a logged-out console, a service
running in Windows session 0, a headless VM: each is a distinct, observable,
self-explaining state — never an ambiguous mid-automation failure on someone's
live screen.

Design:
  * `evaluate()` is a PURE function over `DesktopSignals`, so every state is
    unit-tested without a real (or locked) Windows box.
  * The Win32 probes are the only impure part, isolated at the bottom, and
    they degrade to UNKNOWN rather than lying.
  * `BUSY` is deliberately NOT produced here: whether a runner holds a claim is
    a control-plane fact (it owns the queue). Readiness is host truth only; the
    plane composes the two into the status an operator sees. Two facts, two
    owners, one displayed state.

Used in three places, one source of truth:
  1. `--doctor` (setup): the operator sees the same state and its fix.
  2. Claim gating (worker): a runner that cannot execute never claims work —
     the queue holds it for a healthy runner instead of burning an attempt.
  3. Mid-run guard (worker): if the desktop is lost while a run is in flight,
     the run is stopped through the EXISTING ControlChannel — the engine never
     acts on a black screen and never learns why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# ------------------------------------------------------------------ states
READY = "ready"
LOCKED = "locked"
LOGGED_OUT = "logged_out"
SCREEN_UNAVAILABLE = "screen_unavailable"
PERMISSION_DENIED = "permission_denied"
NETWORK_UNAVAILABLE = "network_unavailable"
UNKNOWN = "unknown"

# Every state carries its own explanation and the exact fix. No ambiguous
# failures: an operator reading a state never has to ask "but why?".
# Pure ASCII: these strings are printed by `--doctor` to Windows consoles that
# are frequently cp1252 and cannot encode typographic punctuation.
_EXPLAIN: dict[str, tuple[str, str]] = {
    READY: ("an interactive desktop session is available and reachable", ""),
    LOCKED: ("the workstation is locked - the input desktop cannot be opened",
             "unlock the console session, or configure this host for unattended "
             "operation (a dedicated auto-login VM); no work was attempted"),
    LOGGED_OUT: ("no user is logged in to the console session",
                 "log a user in to the console session; a runner drives a real desktop"),
    SCREEN_UNAVAILABLE: ("no display is attached to this session",
                         "run on a machine with an interactive desktop (not headless/SSH-only)"),
    PERMISSION_DENIED: ("this process runs in a different Windows session than the "
                        "console and can never reach its desktop",
                        "run the runner as the logged-in console user, not as a "
                        "service/session-0 process or under a different account"),
    NETWORK_UNAVAILABLE: ("the control plane is unreachable from this host",
                          "check RUNNER_PLANE_URL and network egress to the plane"),
    UNKNOWN: ("this host's desktop state could not be determined",
              "run `perceptai-runner --doctor` on the host for detail"),
}

# The only state in which a runner may claim and execute work.
EXECUTABLE = (READY,)

NO_SESSION = 0xFFFFFFFF  # WTS: no active console session attached


@dataclass(frozen=True)
class DesktopSignals:
    """Raw, observed facts about the host. `None` always means "could not
    determine" — never "false". Honest absence beats a confident guess."""
    supported: bool = False                    # Win32 desktop APIs usable here
    console_session: Optional[int] = None      # active console session id
    process_session: Optional[int] = None      # the session this process runs in
    input_desktop_open: Optional[bool] = None  # could we open the input desktop?
    screen_size: Optional[tuple] = None        # (w, h) if a display exists
    plane_reachable: Optional[bool] = None     # None = not checked here


@dataclass(frozen=True)
class Readiness:
    state: str
    detail: str
    fix: str = ""

    @property
    def can_execute(self) -> bool:
        return self.state in EXECUTABLE

    def to_dict(self) -> dict:
        return {"state": self.state, "detail": self.detail, "fix": self.fix,
                "can_execute": self.can_execute}


def _readiness(state: str, extra: str = "") -> Readiness:
    detail, fix = _EXPLAIN[state]
    return Readiness(state=state, detail=f"{detail} ({extra})" if extra else detail, fix=fix)


# -------------------------------------------------------------- pure decision

def evaluate(signals: DesktopSignals) -> Readiness:
    """Map observed signals to exactly one self-explaining state.

    Order matters and encodes the causal hierarchy: a logged-out console has no
    input desktop either, and a session-0 service can never reach the console
    no matter what the lock state is. Reporting the ROOT cause is the whole
    point — an operator must never chase a symptom.
    """
    # The plane being unreachable is a host fact too: the runner cannot receive
    # work or stream evidence, so it must not pretend to be ready.
    if signals.plane_reachable is False:
        return _readiness(NETWORK_UNAVAILABLE)

    if not signals.supported:
        # Non-Windows or Win32 unavailable: fall back to the one honest signal
        # we still have. Never claim LOCKED/LOGGED_OUT we cannot observe.
        if signals.screen_size:
            return _readiness(READY)
        if signals.screen_size is None:
            return _readiness(UNKNOWN, "desktop APIs unavailable on this platform")
        return _readiness(SCREEN_UNAVAILABLE)

    if signals.console_session == NO_SESSION:
        return _readiness(LOGGED_OUT)

    # Running in a different Windows session than the console (session-0
    # service isolation) — structurally unable to reach the user's desktop.
    if (signals.process_session is not None and signals.console_session is not None
            and signals.process_session != signals.console_session):
        return _readiness(
            PERMISSION_DENIED,
            f"process session {signals.process_session} != console session {signals.console_session}")

    if signals.input_desktop_open is False:
        return _readiness(LOCKED)

    if signals.screen_size is None and signals.input_desktop_open is None:
        return _readiness(UNKNOWN)

    if not signals.screen_size:
        return _readiness(SCREEN_UNAVAILABLE)

    return _readiness(READY)


# ------------------------------------------------------------------- probes
# Impure edge. Every probe returns None on any failure so `evaluate` sees
# "unknown" instead of a fabricated fact.

def _win32_signals() -> DesktopSignals:
    import ctypes
    import os

    if os.name != "nt":
        return DesktopSignals(supported=False, screen_size=_screen_size())

    console = process = None
    input_desktop: Optional[bool] = None
    try:
        kernel32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        wtsapi = ctypes.windll.wtsapi32            # type: ignore[attr-defined]
        user32 = ctypes.windll.user32              # type: ignore[attr-defined]

        console = int(wtsapi.WTSGetActiveConsoleSessionId())

        pid = int(kernel32.GetCurrentProcessId())
        sid = ctypes.c_ulong()
        if kernel32.ProcessIdToSessionId(pid, ctypes.byref(sid)):
            process = int(sid.value)

        # The definitive lock test: the input desktop cannot be opened by a
        # process on a locked workstation (Winlogon owns the secure desktop).
        DESKTOP_SWITCHDESKTOP = 0x0100
        handle = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if handle:
            input_desktop = True
            user32.CloseDesktop(handle)
        else:
            input_desktop = False
    except Exception:
        pass  # leave the unknowns as None — evaluate() will say UNKNOWN

    return DesktopSignals(
        supported=True, console_session=console, process_session=process,
        input_desktop_open=input_desktop, screen_size=_screen_size(),
    )


def _screen_size() -> Optional[tuple]:
    try:
        import pyautogui
        size = pyautogui.size()
        return (int(size[0]), int(size[1]))
    except Exception:
        return None


SignalProbe = Callable[[], DesktopSignals]


def probe(signal_probe: SignalProbe = _win32_signals,
          plane_reachable: Optional[bool] = None) -> Readiness:
    """Observe the host and return its one true readiness state."""
    try:
        signals = signal_probe()
    except Exception:
        return _readiness(UNKNOWN, "probe raised")
    if plane_reachable is not None:
        signals = DesktopSignals(
            supported=signals.supported, console_session=signals.console_session,
            process_session=signals.process_session,
            input_desktop_open=signals.input_desktop_open,
            screen_size=signals.screen_size, plane_reachable=plane_reachable,
        )
    return evaluate(signals)
