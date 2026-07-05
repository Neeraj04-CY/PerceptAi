"""SSE transport helpers.

One place that knows how to pump a blocking generator into an async
response with keepalives. Routes own their persistence; this module owns
only the transport mechanics.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import AsyncGenerator, Generator, Optional

KEEPALIVE = ": keepalive\n\n"

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Access-Control-Allow-Origin": "*",
    "Connection": "keep-alive",
}


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def athread_iter(gen: Generator) -> AsyncGenerator[Optional[object], None]:
    """Iterate a blocking generator on a worker thread. Yields its items;
    yields None when idle so callers can emit keepalives."""
    q: queue.Queue = queue.Queue()

    def pump():
        try:
            for item in gen:
                q.put(item)
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(StopIteration)

    threading.Thread(target=pump, daemon=True).start()
    loop = asyncio.get_running_loop()
    while True:
        try:
            item = await loop.run_in_executor(None, lambda: q.get(timeout=0.1))
        except queue.Empty:
            yield None
            continue
        if item is StopIteration:
            return
        yield item
