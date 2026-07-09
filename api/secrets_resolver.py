"""LocalSecretResolver — resolve workspace secrets on the API host.

The engine asks for a secret by NAME; this decrypts the workspace vault value
on demand. It inherits the zeroizing per-run cache from the engine's
CachingSecretResolver: a decrypted value lives only in a bytearray for the run
and is wiped on purge(). Names are loaded once (for the planner); ciphertext is
fetched and decrypted only when a secret is actually used.

Scoping: a session's secrets are its workspace's secrets plus org-wide secrets
(workspace_id NULL). A workspace-scoped secret shadows an org-wide one of the
same name.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from perceptai.secrets import CachingSecretResolver  # noqa: E402

from config import config  # noqa: E402
from secrets_crypto import decrypt, derive_key  # noqa: E402


class LocalSecretResolver(CachingSecretResolver):
    def __init__(self, db, org_id: Optional[str], workspace_id: Optional[str]):
        self._db = db
        self._org = org_id
        self._ws = workspace_id
        self._key = derive_key(config.SECRETS_KEY)
        super().__init__(available=self._load_names())

    def _in_scope(self, row_workspace) -> bool:
        return row_workspace is None or row_workspace == self._ws

    def _load_names(self) -> list[str]:
        if not self._org:
            return []
        try:
            rows = self._db.table("secrets").select("name, workspace_id").eq(
                "org_id", self._org).execute().data or []
        except Exception:
            return []
        return sorted({r["name"] for r in rows if self._in_scope(r.get("workspace_id"))})

    def _fetch(self, name: str) -> Optional[bytes]:
        if not self._org:
            return None
        try:
            rows = self._db.table("secrets").select("ciphertext, workspace_id").eq(
                "org_id", self._org).eq("name", name).execute().data or []
        except Exception:
            return None
        # Workspace-scoped shadows org-wide.
        row = (next((r for r in rows if r.get("workspace_id") == self._ws), None)
               or next((r for r in rows if r.get("workspace_id") is None), None))
        if not row:
            return None
        try:
            return decrypt(row["ciphertext"], self._key).encode("utf-8")
        except Exception:
            return None


def build_local_resolver(db, org_id: Optional[str], workspace_id: Optional[str]):
    """A resolver for the session's scope, or None when nothing is scoped."""
    if not org_id:
        return None
    return LocalSecretResolver(db, org_id, workspace_id)
