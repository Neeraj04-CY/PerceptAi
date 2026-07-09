"""Secret resolution for execution — references in, values out-of-band.

The engine never sees a secret VALUE except at the instant of injection. A
`{{secret:NAME}}` reference travels through the plan, the events, the report and
the cockpit; the value is fetched only at the action layer, typed, and never
recorded. This module owns that resolution and — critically — the value's
lifetime.

Lifetime invariant (enterprise-grade): a resolved value exists only for the run.
It is cached as a mutable `bytearray` so it can be zeroized; `purge()` overwrites
every buffer with zeros and drops the cache, and the engine calls it in a
`finally` around the whole execution (success, terminal failure, or abort). The
cache is per-`SecretResolver` instance (one per run), never module-level, never
persisted, never shared across executions.

CPython caveat, stated honestly: the transient `str` copy handed to the typing
primitive cannot be zeroized (strings are immutable) — it is minimized and
dropped for the garbage collector. The canonical store is the bytearray, which
IS zeroized. This is strictly better than caching values as strings for the run.
"""
from __future__ import annotations

import re
from typing import Optional

_SECRET_RE = re.compile(r"^\{\{\s*secret:\s*([A-Za-z0-9_.\-]+)\s*\}\}$")


def parse_secret_reference(text: str) -> Optional[str]:
    """The secret NAME if `text` is exactly a reference, else None. Only a
    whole-value reference is honored — a secret is never interpolated into a
    larger string (that would leak part of the value into the record)."""
    if not text:
        return None
    match = _SECRET_RE.match(text.strip())
    return match.group(1) if match else None


def mask_reference(name: str) -> str:
    """What gets recorded in place of a typed value."""
    return f"{{{{secret:{name}}}}}"


class SecretResolver:
    """Injected seam (like ControlChannel). Default is a no-op: no secrets are
    available and nothing resolves, so a run behaves exactly as before."""

    def names(self) -> list[str]:
        """Available secret names (never values) — shown to the planner so it
        can emit references."""
        return []

    def resolve(self, name: str) -> Optional[str]:
        return None

    def purge(self) -> None:
        """Zeroize and drop every cached value. Idempotent."""


class NullSecretResolver(SecretResolver):
    """The kernel default — resolves nothing."""


class CachingSecretResolver(SecretResolver):
    """Per-run resolver: fetch once, cache as a zeroable bytearray, destroy on
    purge(). Subclasses implement `_fetch`; the lifetime guarantees live here."""

    def __init__(self, available: Optional[list[str]] = None):
        self._available = list(available or [])
        self._cache: dict[str, bytearray] = {}

    def names(self) -> list[str]:
        return list(self._available)

    def resolve(self, name: str) -> Optional[str]:
        if name not in self._available:
            return None
        if name not in self._cache:
            raw = self._fetch(name)
            if raw is None:
                return None
            self._cache[name] = bytearray(raw)
        return self._cache[name].decode("utf-8", "replace")

    def _fetch(self, name: str) -> Optional[bytes]:
        """Retrieve the raw value bytes. Subclass responsibility."""
        return None

    def purge(self) -> None:
        for buf in self._cache.values():
            for i in range(len(buf)):
                buf[i] = 0
        self._cache.clear()
