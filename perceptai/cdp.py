"""Chrome DevTools Protocol access for the DOM perception provider.

Minimal and lazy on purpose: `list_pages` is stdlib (`urllib`), the websocket
is imported only when a real read happens, and any failure degrades to None so
the provider simply contributes nothing (pixels stay the floor). No CDP detail
leaks past this module — the provider consumes a normalized `DomSnapshot`.

Two layers:
  * `CDPClient` / `_Session` — the wire: list debuggable pages, open a socket,
    send commands, ignore events.
  * `CDPAccessibilityReader` — reads the foreground tab's ACCESSIBILITY tree
    (roles + names, per the chosen design) and joins it to DOMSnapshot geometry
    by backend node id, returning a `DomSnapshot` in screen coordinates.

The coordinate math (viewport CSS px -> screen px through the browser chrome)
is a real-screen heuristic: it is validated by the perception bench with a real
browser open, not by unit tests. Everything the provider does with a
`DomSnapshot` is pure and unit-tested against a fake reader.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# JS that reports the browser window geometry needed to place viewport
# coordinates on the OS screen. All values are CSS pixels (the input space
# PerceptAI clicks in when the process is DPI-unaware).
_GEO_JS = (
    "({dpr:window.devicePixelRatio,"
    " sx:window.screenX,sy:window.screenY,"
    " ow:window.outerWidth,iw:window.innerWidth,"
    " oh:window.outerHeight,ih:window.innerHeight,"
    " sX:window.scrollX,sY:window.scrollY})"
)


@dataclass
class DomNode:
    """One accessible element, geometry in CSS px relative to the viewport."""
    role: str
    name: str
    x: float
    y: float
    w: float
    h: float
    focusable: bool = False
    disabled: bool = False
    secure: bool = False   # <input type=password> — the secrets layer's guard
    value: str = ""


@dataclass
class DomSnapshot:
    """Normalized read of one browser tab. `origin` is the content area's
    top-left on the OS screen (CSS px); the provider translates each node's
    viewport rect by it. `dpr` is carried for future refinement."""
    url: str = ""
    title: str = ""
    origin: tuple[int, int] = (0, 0)
    dpr: float = 1.0
    nodes: list[DomNode] = field(default_factory=list)


class DomReader(Protocol):
    def read(self, host: str, port: int, foreground_title: str, *,
             max_nodes: int, timeout_s: float) -> Optional[DomSnapshot]: ...


# ------------------------------------------------------------------ the wire

class _Session:
    def __init__(self, ws):
        self._ws = ws
        self._id = 0

    def command(self, method: str, params: Optional[dict] = None) -> dict:
        self._id += 1
        mid = self._id
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
            # otherwise a protocol event — ignore

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


class CDPClient:
    def __init__(self, host: str, port: int, timeout_s: float = 2.0):
        self._host = host
        self._port = port
        self._timeout = timeout_s

    def list_pages(self) -> list[dict]:
        url = f"http://{self._host}:{self._port}/json"
        with urllib.request.urlopen(url, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def open(self, ws_url: str) -> _Session:
        import websocket  # lazy: only when a real read happens
        return _Session(websocket.create_connection(ws_url, timeout=self._timeout))


# --------------------------------------------------------- accessibility read

class CDPAccessibilityReader:
    """Reads the foreground tab's AX tree and joins it to DOMSnapshot geometry.
    Defensive throughout — any failure returns None and the provider falls back
    to pixels."""

    def __init__(self, client_factory=CDPClient):
        self._client_factory = client_factory

    def read(self, host: str, port: int, foreground_title: str, *,
             max_nodes: int, timeout_s: float) -> Optional[DomSnapshot]:
        try:
            client = self._client_factory(host, port, timeout_s)
            pages = [p for p in client.list_pages()
                     if p.get("type") == "page" and p.get("webSocketDebuggerUrl")]
            if not pages:
                return None
            page = self._pick_page(pages, foreground_title)
            session = client.open(page["webSocketDebuggerUrl"])
            try:
                session.command("DOM.enable")
                session.command("Accessibility.enable")
                ax = session.command("Accessibility.getFullAXTree")
                snap = session.command("DOMSnapshot.captureSnapshot", {"computedStyles": []})
                geo = (session.command("Runtime.evaluate",
                                       {"expression": _GEO_JS, "returnByValue": True})
                       .get("result", {}).get("value", {})) or {}
            finally:
                session.close()
            return self._build(ax, snap, geo, page, max_nodes)
        except Exception:
            return None

    @staticmethod
    def _pick_page(pages: list[dict], foreground_title: str) -> dict:
        """Prefer the page whose title matches the foreground window; else the
        first debuggable page."""
        title = (foreground_title or "").lower()
        if title:
            for p in pages:
                if p.get("title") and p["title"].lower() in title:
                    return p
        return pages[0]

    @staticmethod
    def _content_origin(geo: dict) -> tuple[int, int]:
        """Content-area top-left on screen (CSS px). Top chrome is the window's
        outer/inner height delta; side borders are usually ~0."""
        sx = int(geo.get("sx", 0))
        sy = int(geo.get("sy", 0))
        top_chrome = int(geo.get("oh", 0)) - int(geo.get("ih", 0))
        side = (int(geo.get("ow", 0)) - int(geo.get("iw", 0))) // 2
        return (sx + max(0, side), sy + max(0, top_chrome))

    def _build(self, ax: dict, snap: dict, geo: dict, page: dict,
               max_nodes: int) -> Optional[DomSnapshot]:
        bounds = self._bounds_by_backend_id(snap)
        if not bounds:
            return None
        secure_ids = self._secure_backend_ids(snap)
        origin = self._content_origin(geo)
        nodes: list[DomNode] = []
        for ax_node in ax.get("nodes", []) or []:
            if len(nodes) >= max_nodes:
                break
            node = self._ax_to_node(ax_node, bounds, secure_ids)
            if node is not None:
                nodes.append(node)
        return DomSnapshot(
            url=str(page.get("url", "")), title=str(page.get("title", "")),
            origin=origin, dpr=float(geo.get("dpr", 1.0) or 1.0), nodes=nodes,
        )

    @staticmethod
    def _bounds_by_backend_id(snap: dict) -> dict[int, tuple[float, float, float, float]]:
        """backendNodeId -> (x, y, w, h) in CSS px, from the DOMSnapshot layout
        tree. Rects are viewport-relative after subtracting document scroll,
        which captureSnapshot already reports document-relative; we keep them as
        given and let scroll be handled by the layout viewport."""
        out: dict[int, tuple[float, float, float, float]] = {}
        for doc in snap.get("documents", []) or []:
            backend_ids = (doc.get("nodes", {}) or {}).get("backendNodeId", []) or []
            layout = doc.get("layout", {}) or {}
            node_index = layout.get("nodeIndex", []) or []
            rects = layout.get("bounds", []) or []
            for i, ni in enumerate(node_index):
                if i >= len(rects) or ni >= len(backend_ids):
                    continue
                r = rects[i]
                if not r or len(r) < 4 or r[2] <= 0 or r[3] <= 0:
                    continue
                out[int(backend_ids[ni])] = (float(r[0]), float(r[1]), float(r[2]), float(r[3]))
        return out

    @staticmethod
    def _ax_prop(ax_node: dict, name: str) -> Any:
        for p in ax_node.get("properties", []) or []:
            if p.get("name") == name:
                return (p.get("value") or {}).get("value")
        return None

    @staticmethod
    def _secure_backend_ids(snap: dict) -> set[int]:
        """backendNodeId of every <input type=password> — the fields the
        secrets layer is allowed to type into. From the DOMSnapshot node table
        (nodeName + attributes are string-table indices)."""
        strings = snap.get("strings", []) or []

        def s(i: int) -> str:
            return strings[i] if 0 <= i < len(strings) else ""

        ids: set[int] = set()
        for doc in snap.get("documents", []) or []:
            nodes = doc.get("nodes", {}) or {}
            names = nodes.get("nodeName", []) or []
            backend = nodes.get("backendNodeId", []) or []
            attrs = nodes.get("attributes", []) or []
            for i, backend_id in enumerate(backend):
                if i >= len(names) or s(names[i]).upper() != "INPUT":
                    continue
                a = attrs[i] if i < len(attrs) else []
                for j in range(0, len(a) - 1, 2):
                    if s(a[j]).lower() == "type" and s(a[j + 1]).lower() == "password":
                        ids.add(int(backend_id))
        return ids

    def _ax_to_node(self, ax_node: dict,
                    bounds: dict[int, tuple[float, float, float, float]],
                    secure_ids: set[int]) -> Optional[DomNode]:
        if ax_node.get("ignored"):
            return None
        backend_id = ax_node.get("backendDOMNodeId")
        if backend_id is None or int(backend_id) not in bounds:
            return None
        role = str((ax_node.get("role") or {}).get("value", "")).strip().lower()
        name = str((ax_node.get("name") or {}).get("value", "")).strip()
        if not role or role in ("none", "generic", "presentation"):
            return None
        x, y, w, h = bounds[int(backend_id)]
        return DomNode(
            role=role, name=name, x=x, y=y, w=w, h=h,
            focusable=bool(self._ax_prop(ax_node, "focusable")),
            disabled=bool(self._ax_prop(ax_node, "disabled")),
            secure=int(backend_id) in secure_ids,
            value=str((ax_node.get("value") or {}).get("value", "") or ""),
        )
