"""Compatibility shim — the signing protocol now lives in perceptai.signing
(the single dependency both plane and runner share). Kept so api's flat
imports (`from runner_signing import ...`) keep working; do not add logic here.
"""
from perceptai.signing import (  # noqa: F401
    ED25519,
    HMAC_SHA256,
    derive_runner_key,
    private_key_from_seed,
    public_key_for,
    sign_work_order,
    sign_work_order_ed25519,
    verify_request,
    verify_work_order,
    verify_work_order_ed25519,
)
