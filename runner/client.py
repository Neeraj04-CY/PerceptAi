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
    def __init__(self, config: RunnerConfig, identity=None):
        self._c = config
        self._identity = identity
        self._s = requests.Session()
        self._s.headers.update({
            "X-Runner-Token": config.token,
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self._c.plane_url}{path}"

    def _path(self, path: str) -> str:
        """The URL path the plane will see — what the signature must bind to."""
        from urllib.parse import urlparse
        return urlparse(self._url(path)).path

    def _signed(self, method: str, path: str, body: Optional[dict]) -> tuple[bytes, dict]:
        """Serialize once, sign those exact bytes, send exactly them. Signing a
        re-serialized copy would be a signature over something we never sent."""
        import json as _json
        raw = _json.dumps(body).encode() if body is not None else b""
        headers: dict = {}
        if self._identity is not None:
            headers = self._identity.sign(method, self._path(path), raw)
        return raw, headers

    def _post(self, path: str, body: Optional[dict] = None, **kw):
        raw, headers = self._signed("POST", path, body)
        return self._s.post(self._url(path), data=raw, headers=headers,
                            timeout=self._c.request_timeout_s, **kw)

    def _get(self, path: str, **kw):
        _raw, headers = self._signed("GET", path, None)
        return self._s.get(self._url(path), headers=headers,
                           timeout=self._c.request_timeout_s, **kw)

    def enroll(self, public_key: str) -> dict:
        """Publish our public key once. Returns the plane's public key."""
        r = self._post("/runners/enroll", {"public_key": public_key})
        r.raise_for_status()
        return r.json()

    def ping(self) -> None:
        """Unauthenticated reachability probe for the doctor."""
        self._s.get(self._url("/platform/health"),
                    timeout=self._c.request_timeout_s).raise_for_status()

    def heartbeat(self, current_session_id: Optional[str],
                  readiness: Optional[dict] = None) -> None:
        """Liveness + session truth. Readiness rides the heartbeat so an unready
        host is visible in the fleet view WITH its reason, instead of looking
        like a runner that silently stopped taking work."""
        self._post("/runners/heartbeat",
                   {"current_session_id": current_session_id,
                    "readiness": readiness}).raise_for_status()

    def claim(self) -> Optional[dict]:
        r = self._post("/runners/claim")
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def post_events(self, session_id: str, events: list[dict]) -> None:
        self._post(f"/runners/executions/{session_id}/events",
                   {"events": events}).raise_for_status()

    def post_result(self, session_id: str, report: dict) -> None:
        self._post(f"/runners/executions/{session_id}/result", report).raise_for_status()

    # --- control transport (read durable control the operator set) ---

    def get_control(self, session_id: str) -> dict:
        r = self._get(f"/runners/executions/{session_id}/control")
        r.raise_for_status()
        return r.json()

    def post_approval_request(self, session_id: str, request: dict) -> None:
        self._post(f"/runners/executions/{session_id}/approval-request",
                   {"request": request}).raise_for_status()

    # --- secret transport (fetch one value over TLS, on demand) ---

    def fetch_secret(self, session_id: str, name: str) -> Optional[str]:
        r = self._post(f"/runners/executions/{session_id}/secrets", {"name": name})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("value")
