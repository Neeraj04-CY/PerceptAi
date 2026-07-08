"""Compatibility shim — the signing protocol now lives in perceptai.signing
(the single dependency both plane and runner share). Kept so api's flat
imports (`from runner_signing import ...`) keep working; do not add logic here.
"""
from perceptai.signing import (  # noqa: F401
    derive_runner_key,
    sign_work_order,
    verify_work_order,
)
