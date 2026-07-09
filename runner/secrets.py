"""RemoteSecretResolver — resolve secrets on a runner over the control plane.

The runner never holds the vault: it knows only the secret NAMES from its work
order, and fetches a value on demand over an authorized channel at the instant
of injection. It inherits the engine's zeroizing per-run cache — a fetched value
lives only in a bytearray for the run and is wiped when the run ends (the
AgentSession purges in its `finally`). Never persisted, never shared.
"""
from __future__ import annotations

from typing import Optional, Protocol

from perceptai.secrets import CachingSecretResolver


class SecretTransport(Protocol):
    def fetch_secret(self, session_id: str, name: str) -> Optional[str]: ...


class RemoteSecretResolver(CachingSecretResolver):
    def __init__(self, client: SecretTransport, session_id: str,
                 available: Optional[list[str]] = None):
        super().__init__(available=list(available or []))
        self._client = client
        self._session_id = session_id

    def _fetch(self, name: str) -> Optional[bytes]:
        try:
            value = self._client.fetch_secret(self._session_id, name)
        except Exception:
            return None
        return value.encode("utf-8") if value is not None else None
