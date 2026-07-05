"""Symmetric encryption for the secrets vault.

Fernet (AES-128-CBC + HMAC) with a key derived from the server secret.
Pure functions with the key injected — testable without config, and the
key source can move to a KMS later without touching callers' shapes.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def derive_key(server_secret: str) -> bytes:
    """A stable Fernet key from the server secret. Deterministic so every
    API process with the same secret can decrypt."""
    digest = hashlib.sha256(f"perceptai.secrets.v1:{server_secret}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(value: str, key: bytes) -> str:
    return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str, key: bytes) -> str:
    """Raises ValueError on tampered/foreign ciphertext — callers surface
    a clean 409 instead of a stack trace."""
    try:
        return Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("secret cannot be decrypted with this server key") from e
