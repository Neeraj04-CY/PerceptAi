"""HTTP control-plane client — the runner's only transport.

Implements the ControlPlane protocol the worker depends on. Pull-only: the
runner opens outbound requests to the plane and never listens for inbound
connections, so it needs no public address and works behind NAT.
"""
from __future__ import annotations

from typing import Optional

from .config import RunnerConfig

try:
    import requests
except ImportError as e:  # pragma: no cover - only hit when actually running
    raise SystemExit(
        "The runner needs `requests` (pip install requests). "
        "Tests don't — they inject a fake transport."
    ) from e


class HttpControlPlane:
    def __init__(self, config: RunnerConfig):
        self._c = config
        self._s = requests.Session()
        self._s.headers.update({
            "X-Runner-Token": config.token,
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self._c.plane_url}{path}"

    def heartbeat(self, current_session_id: Optional[str]) -> None:
        self._s.post(self._url("/runners/heartbeat"),
                     json={"current_session_id": current_session_id},
                     timeout=self._c.request_timeout_s).raise_for_status()

    def claim(self) -> Optional[dict]:
        r = self._s.post(self._url("/runners/claim"), timeout=self._c.request_timeout_s)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def post_events(self, session_id: str, events: list[dict]) -> None:
        self._s.post(self._url(f"/runners/executions/{session_id}/events"),
                     json={"events": events},
                     timeout=self._c.request_timeout_s).raise_for_status()

    def post_result(self, session_id: str, report: dict) -> None:
        self._s.post(self._url(f"/runners/executions/{session_id}/result"),
                     json=report,
                     timeout=self._c.request_timeout_s).raise_for_status()

    # --- control transport (read durable control the operator set) ---

    def get_control(self, session_id: str) -> dict:
        r = self._s.get(self._url(f"/runners/executions/{session_id}/control"),
                        timeout=self._c.request_timeout_s)
        r.raise_for_status()
        return r.json()

    def post_approval_request(self, session_id: str, request: dict) -> None:
        self._s.post(self._url(f"/runners/executions/{session_id}/approval-request"),
                     json={"request": request},
                     timeout=self._c.request_timeout_s).raise_for_status()
