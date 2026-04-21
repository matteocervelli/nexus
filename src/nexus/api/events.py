"""SSE endpoint for broadcasting live agent lifecycle events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from nexus.api.deps import get_event_bus
from nexus.events import EventBus

router = APIRouter(prefix="/nexus/api", tags=["events"])

# Keepalive comment sent when no events arrive within this window (seconds).
# Exposed as module-level constant so tests can monkeypatch it.
_KEEPALIVE_TIMEOUT = 30.0


async def sse_generator(
    event_bus: EventBus,
    keepalive_timeout: float = _KEEPALIVE_TIMEOUT,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE frames from the event bus.

    Emits ``data: <json>\\n\\n`` for each event.
    Emits ``: keepalive\\n\\n`` when no event arrives within keepalive_timeout.
    Unsubscribes from the bus on cleanup (cancelled or normal exit).
    """
    q = event_bus.subscribe()
    try:
        while True:
            try:
                evt = await asyncio.wait_for(q.get(), timeout=keepalive_timeout)
                yield f"data: {json.dumps(evt)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        event_bus.unsubscribe(q)


@router.get("/events")
async def events_stream(event_bus: EventBus = Depends(get_event_bus)) -> StreamingResponse:
    """Stream lifecycle events as Server-Sent Events (text/event-stream).

    Each frame: ``data: <json>\\n\\n``.
    Keepalive comment ``: keepalive\\n\\n`` sent every _KEEPALIVE_TIMEOUT seconds.
    """
    return StreamingResponse(
        sse_generator(event_bus),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
