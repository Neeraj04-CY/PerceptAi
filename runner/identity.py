"""Runner identity — a private key that never leaves this machine.

Before Chapter IX a runner's credential was a bearer token plus a symmetric
signing key that the PLANE could also derive. Anyone holding either could be
that runner, and one server secret could forge work for the whole fleet.

Now:
  * The runner generates an Ed25519 keypair locally, on first start.
  * The private half is written to disk with owner-only permissions and is
    never transmitted, logged, or recoverable from the control plane.
  * The public half is enrolled with the plane once (trust on first use), after
    which the plane verifies every request against it.
  * The plane's own public key is stored alongside, so the runner can verify
    that a work order really came from the plane — without holding any secret
    capable of issuing one.

Blast radius: compromise this file and you compromise exactly this runner.
"""
from __future__ import annotations

import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from perceptai.signing import (
    ED25519,
    generate_keypair,
    public_key_for,
    sign_request,
    verify_work_order_ed25519,
)

DEFAULT_IDENTITY_PATH = Path.home() / ".perceptai" / "runner_identity.json"


@dataclass
class RunnerIdentity:
    """This host's cryptographic identity, plus the plane's public key."""
    private_key: str
    public_key: str
    plane_public_key: str = ""
    enrolled: bool = False

    # ------------------------------------------------------------- storage
    @classmethod
    def load_or_create(cls, path: Optional[Path] = None) -> "RunnerIdentity":
        path = Path(path or DEFAULT_IDENTITY_PATH)
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                return cls(private_key=raw["private_key"],
                           public_key=raw.get("public_key") or public_key_for(raw["private_key"]),
                           plane_public_key=raw.get("plane_public_key", ""),
                           enrolled=bool(raw.get("enrolled")))
            except Exception:
                pass  # corrupt identity: regenerate rather than refuse to start
        private, public = generate_keypair()
        identity = cls(private_key=private, public_key=public)
        identity.save(path)
        return identity

    def save(self, path: Optional[Path] = None) -> None:
        path = Path(path or DEFAULT_IDENTITY_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "private_key": self.private_key,
            "public_key": self.public_key,
            "plane_public_key": self.plane_public_key,
            "enrolled": self.enrolled,
        }))
        try:
            # Owner-only. On Windows this is advisory (NTFS ACLs govern), which
            # is why hardware-backed key storage is the documented next step.
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    # ------------------------------------------------------------ protocol
    def sign(self, method: str, path: str, body: bytes) -> dict[str, str]:
        """The headers that prove this request came from this runner."""
        import time
        timestamp = int(time.time())
        nonce = uuid.uuid4().hex
        return {
            "X-Runner-Signature": sign_request(self.private_key, method, path,
                                               body, timestamp, nonce),
            "X-Runner-Timestamp": str(timestamp),
            "X-Runner-Nonce": nonce,
        }

    def verify_work_order(self, order: dict, signature: str) -> bool:
        """Did the plane really issue this order? Verified with the plane's
        PUBLIC key: the runner holds nothing that could forge one."""
        if not self.plane_public_key:
            return False
        return verify_work_order_ed25519(self.plane_public_key, order, signature)

    def algorithm(self) -> str:
        return ED25519
