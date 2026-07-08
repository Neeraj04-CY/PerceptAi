"""Reuse the control plane's signing protocol — one source of truth.

The signature contract is defined once, in api/runner_signing.py (pure stdlib).
The runner imports it rather than re-implementing it, so plane and runner can
never drift. A packaged standalone runner would vendor that single module; here
the runner runs from the repo checkout and imports it directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parent.parent / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from runner_signing import verify_work_order  # noqa: E402,F401
