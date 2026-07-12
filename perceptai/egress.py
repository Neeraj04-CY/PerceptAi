"""Data egress control — a company always knows what leaves its machine.

An enterprise deploying a screen-reading agent is handing a third-party model
its ERP, its payroll screen, its customers' records. Before Chapter IX the
vision provider base64-encoded screenshots of that desktop and posted them to a
cloud model with no switch, no policy and no record. That is the finding a
Fortune 500 security review lands on in week one.

Five questions must always have an answer, from the record, after the fact:
    what left the machine, why it left, where it went, what model received it,
    and which policy allowed it.

DESIGN
  * Policy is DATA (`EgressPolicy`), owned by the workspace, never a hardcoded
    security decision in a route or a provider.
  * Enforcement lives at ONE checkpoint — `llm.py`, the engine's single LLM
    access point. Nothing reaches a model without passing it, so a new call
    site cannot forget to ask.
  * The vision provider ALSO consults the policy in `available()`. That is data
    minimization, not a second gate: when pixels may not leave, we never even
    encode the screenshot.
  * Every decision (allowed or blocked) is emitted on the canonical event
    stream. Metadata only: sizes, counts, model, purpose — never content.

MODES
  allow       (default) observations may be sent to the configured model.
  redact      observations are sent with sensitive spans deterministically
              removed. The customer trades fidelity for confidentiality.
  local_only  no PIXELS leave: the vision provider is disabled and screenshots
              are never transmitted. Text still may (subject to redaction).
              Pixels remain the perception floor LOCALLY via OCR/UIA, so the
              agent keeps working on any application.
  deny        nothing observed may reach any model. The engine cannot plan from
              the screen, so a run is REFUSED UP FRONT with a named reason
              rather than half-executing and failing obscurely. Honest, not
              silently degraded. (A local-model deployment is what makes this
              mode useful; that is a deliberate future step, not a pretence.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

ALLOW = "allow"
REDACT = "redact"
LOCAL_ONLY = "local_only"
DENY = "deny"
MODES = (ALLOW, REDACT, LOCAL_ONLY, DENY)

TEXT = "text"
PIXELS = "pixels"


# ------------------------------------------------------------- redaction
# Deterministic, explainable classes. Each is bounded and conservative: a
# redactor that eats ordinary UI text would silently destroy the agent's
# ability to work, which is its own kind of outage.
_REDACTORS: tuple[tuple[str, re.Pattern], ...] = (
    ("email", re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk|whsec)[-_][A-Za-z0-9_\-]{16,}\b")),
    ("phone", re.compile(r"\b\+?\d{1,3}[ .-]?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")),
)
_REDACTOR_NAMES = tuple(name for name, _ in _REDACTORS)


def redact(text: str, classes: tuple[str, ...],
           custom_patterns: tuple[str, ...] = ()) -> tuple[str, int]:
    """Remove sensitive spans. Returns (redacted_text, count). Deterministic:
    the same screen always redacts identically, so prompts stay stable and the
    reasoning-consistency guarantee holds."""
    if not text:
        return text, 0
    count = 0
    for name, pattern in _REDACTORS:
        if name not in classes:
            continue
        text, n = pattern.subn(f"[REDACTED:{name}]", text)
        count += n
    for raw in custom_patterns:
        try:
            text, n = re.subn(raw, "[REDACTED:custom]", text)
            count += n
        except re.error:
            continue  # a bad customer regex must never break execution
    return text, count


# ---------------------------------------------------------------- policy

@dataclass(frozen=True)
class EgressPolicy:
    """Workspace policy, as data. Unknown/malformed values fail SAFE toward the
    documented default (allow) rather than silently denying every run — an
    egress policy that bricks the fleet on a typo is its own incident. The one
    exception: an explicitly-named mode is always honored exactly."""
    mode: str = ALLOW
    redact_classes: tuple[str, ...] = field(default_factory=tuple)
    custom_patterns: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "EgressPolicy":
        raw = raw or {}
        mode = str(raw.get("mode", ALLOW) or ALLOW).lower()
        if mode not in MODES:
            mode = ALLOW
        classes = tuple(c for c in (raw.get("redact") or ()) if c in _REDACTOR_NAMES)
        if mode == REDACT and not classes:
            classes = _REDACTOR_NAMES     # redact mode with no list means "all"
        return cls(mode=mode, redact_classes=classes,
                   custom_patterns=tuple(str(p) for p in (raw.get("custom_patterns") or ())))

    # What may cross the boundary
    @property
    def allows_text(self) -> bool:
        return self.mode != DENY

    @property
    def allows_pixels(self) -> bool:
        return self.mode in (ALLOW, REDACT)

    @property
    def redacts(self) -> bool:
        return bool(self.redact_classes or self.custom_patterns)

    def reason(self, kind: str) -> str:
        """Why this data may or may not leave — in an auditor's words."""
        if kind == PIXELS and not self.allows_pixels:
            if self.mode == LOCAL_ONLY:
                return ("workspace policy is local_only: screenshots never leave "
                        "this machine (text perception continues locally)")
            return "workspace policy denies all egress of observations"
        if kind == TEXT and not self.allows_text:
            return "workspace policy denies all egress of observations"
        if self.redacts:
            return f"workspace policy allows egress with redaction: {', '.join(self.redact_classes) or 'custom'}"
        return "workspace policy allows egress"

    def to_dict(self) -> dict:
        return {"mode": self.mode, "redact": list(self.redact_classes),
                "custom_patterns": list(self.custom_patterns)}


ALLOW_ALL = EgressPolicy()


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    kind: str            # text | pixels
    mode: str
    reason: str
    model: str = ""
    purpose: str = ""    # plan | heal | verify | report | perceive
    size: int = 0        # characters (text) or bytes (pixels) — never content
    redactions: int = 0

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "kind": self.kind, "mode": self.mode,
                "reason": self.reason, "model": self.model, "purpose": self.purpose,
                "size": self.size, "redactions": self.redactions}


class EgressDenied(RuntimeError):
    """Policy forbade sending observations to a model. Raised only where the
    caller is expected to refuse honestly (never swallowed into a bad plan)."""

    def __init__(self, decision: EgressDecision):
        super().__init__(decision.reason)
        self.decision = decision


# ----------------------------------------------------------------- guard

class EgressGuard:
    """The checkpoint. Injected into the LLM client (and consulted by the vision
    provider), so every byte that leaves the machine is decided in one place and
    recorded on the canonical event stream."""

    def __init__(self, policy: Optional[EgressPolicy] = None,
                 emit: Optional[Callable[[EgressDecision], None]] = None):
        self.policy = policy or ALLOW_ALL
        self._emit = emit
        self._seen: set[tuple] = set()   # dedup identical decisions per run

    # --- queries used for data minimization, before anything is prepared ---
    @property
    def allows_text(self) -> bool:
        return self.policy.allows_text

    @property
    def allows_pixels(self) -> bool:
        return self.policy.allows_pixels

    def _record(self, decision: EgressDecision) -> EgressDecision:
        if self._emit is None:
            return decision
        # Blocked decisions are always news. Allowed ones are deduped per
        # (kind, purpose, model) so a 30-step run doesn't emit 30 identical rows.
        key = (decision.allowed, decision.kind, decision.purpose, decision.model)
        if not decision.allowed or key not in self._seen:
            self._seen.add(key)
            try:
                self._emit(decision)
            except Exception:
                pass  # observability must never break execution
        return decision

    def text(self, prompt: str, *, model: str, purpose: str) -> tuple[str, EgressDecision]:
        """Gate + transform outbound text. Returns the text that may actually be
        sent. Raises EgressDenied when policy forbids text egress entirely."""
        policy = self.policy
        if not policy.allows_text:
            decision = self._record(EgressDecision(
                allowed=False, kind=TEXT, mode=policy.mode, reason=policy.reason(TEXT),
                model=model, purpose=purpose, size=len(prompt or "")))
            raise EgressDenied(decision)

        out, n = (prompt, 0)
        if policy.redacts:
            out, n = redact(prompt, policy.redact_classes, policy.custom_patterns)
        decision = self._record(EgressDecision(
            allowed=True, kind=TEXT, mode=policy.mode, reason=policy.reason(TEXT),
            model=model, purpose=purpose, size=len(out), redactions=n))
        return out, decision

    def pixels(self, *, model: str, purpose: str, size: int = 0) -> EgressDecision:
        """Gate outbound pixels. Never raises: when screenshots may not leave,
        the vision provider simply degrades and the local providers carry on —
        pixels remain the perception floor, on this machine."""
        policy = self.policy
        allowed = policy.allows_pixels
        return self._record(EgressDecision(
            allowed=allowed, kind=PIXELS, mode=policy.mode, reason=policy.reason(PIXELS),
            model=model, purpose=purpose, size=size))


NULL_GUARD = EgressGuard(ALLOW_ALL)


def guard_from(policy: Any) -> EgressGuard:
    """Accept a policy dict, an EgressPolicy, an EgressGuard, or None."""
    if isinstance(policy, EgressGuard):
        return policy
    if isinstance(policy, EgressPolicy):
        return EgressGuard(policy)
    if isinstance(policy, dict):
        return EgressGuard(EgressPolicy.from_dict(policy))
    return EgressGuard(ALLOW_ALL)
