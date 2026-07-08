"""Reuse the shared signing protocol — one source of truth.

The signature contract is defined once, in perceptai.signing (pure stdlib), and
imported by both the control plane and the runner so they can never drift. The
runner depends on the engine already, so this is a clean package import with no
path hacks — and the runner wheel is self-contained.
"""
from perceptai.signing import verify_work_order  # noqa: F401
