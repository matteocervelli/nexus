"""TDD tests for EventBus and GET /nexus/api/events SSE endpoint."""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from nexus.events import EventBus, EventType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# Task 1: EventBus pub/sub unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_publish_fans_out_to_all_subscribers(bus: EventBus) -> None:
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    await bus.publish(EventType.AGENT_SPAWNED, {"work_item_id": "abc"})

    evt1 = q1.get_nowait()
    evt2 = q2.get_nowait()
    assert evt1["type"] == "agent_spawned"
    assert evt2["type"] == "agent_spawned"
    assert evt1["data"] == evt2["data"]


@pytest.mark.asyncio
async def test_event_bus_unsubscribe_removes_queue(bus: EventBus) -> None:
    q = bus.subscribe()
    bus.unsubscribe(q)

    await bus.publish(EventType.WORK_ITEM_STATUS_CHANGED, {"status": "running"})

    assert q.empty()


@pytest.mark.asyncio
async def test_event_bus_publish_drops_on_full_queue(bus: EventBus) -> None:
    q = bus.subscribe()
    # Fill the queue to maxsize
    for _i in range(bus._queue_maxsize):
        q.put_nowait({"type": "dummy", "data": {}, "ts": "2026-01-01T00:00:00Z"})

    # Should not raise even when queue is full
    await bus.publish(EventType.BUDGET_ALERT, {"agent_role": "code-agent"})

    assert q.full()


@pytest.mark.asyncio
async def test_event_bus_publish_payload_includes_type_data_ts(bus: EventBus) -> None:
    q = bus.subscribe()
    await bus.publish(EventType.AGENT_COMPLETED, {"work_item_id": "xyz", "status": "done"})

    evt = q.get_nowait()
    assert evt["type"] == "agent_completed"
    assert evt["data"]["work_item_id"] == "xyz"
    assert "ts" in evt
    # ts should be parseable ISO-8601
    from datetime import datetime

    datetime.fromisoformat(evt["ts"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_event_bus_subscriber_count(bus: EventBus) -> None:
    assert bus.subscriber_count == 0
    q1 = bus.subscribe()
    assert bus.subscriber_count == 1
    q2 = bus.subscribe()
    assert bus.subscriber_count == 2
    bus.unsubscribe(q1)
    assert bus.subscriber_count == 1
    bus.unsubscribe(q2)
    assert bus.subscriber_count == 0


# ---------------------------------------------------------------------------
# Task 2: SSE endpoint tests — test sse_generator directly to avoid
# httpx ASGITransport limitation with non-terminating streams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_endpoint_returns_streaming_response(bus: EventBus) -> None:
    """events_stream() returns a StreamingResponse with correct content-type."""
    from fastapi.responses import StreamingResponse

    from nexus.api.events import events_stream

    response = await events_stream(event_bus=bus)
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_sse_generator_yields_data_frame(bus: EventBus) -> None:
    """Generator yields ``data: <json>\\n\\n`` after a publish."""
    from nexus.api.events import sse_generator

    gen = sse_generator(bus, keepalive_timeout=5.0)

    # Start the generator in a task so it subscribes before we publish
    task = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)  # yield to let generator reach q.get() (subscribed)

    await bus.publish(EventType.AGENT_SPAWNED, {"work_item_id": "abc", "agent_role": "code-agent"})

    frame = await task
    await gen.aclose()

    assert frame.startswith("data:")
    payload = json.loads(frame[len("data:") :].strip())
    assert payload["type"] == "agent_spawned"
    assert payload["data"]["work_item_id"] == "abc"
    assert "ts" in payload


@pytest.mark.asyncio
async def test_sse_generator_yields_keepalive_on_timeout(bus: EventBus) -> None:
    """Generator emits keepalive comment when no event arrives within timeout."""
    from nexus.api.events import sse_generator

    gen = sse_generator(bus, keepalive_timeout=0.05)
    frame = await gen.__anext__()
    await gen.aclose()

    assert frame == ": keepalive\n\n"


@pytest.mark.asyncio
async def test_sse_generator_fans_out_multiple_events(bus: EventBus) -> None:
    """Generator yields one frame per event in order."""
    from nexus.api.events import sse_generator

    gen = sse_generator(bus, keepalive_timeout=5.0)

    # Collect two frames via a task; publish after generator subscribes
    frames: list[str] = []

    async def collect_two():
        frames.append(await gen.__anext__())
        frames.append(await gen.__anext__())

    task = asyncio.create_task(collect_two())
    await asyncio.sleep(0)  # let generator subscribe

    await bus.publish(EventType.AGENT_SPAWNED, {"seq": 1})
    await bus.publish(EventType.AGENT_COMPLETED, {"seq": 2})

    await task
    await gen.aclose()

    p1 = json.loads(frames[0][len("data:") :].strip())
    p2 = json.loads(frames[1][len("data:") :].strip())
    assert p1["type"] == "agent_spawned"
    assert p2["type"] == "agent_completed"


@pytest.mark.asyncio
async def test_sse_generator_cleanup_on_close(bus: EventBus) -> None:
    """aclose() unsubscribes the queue from the bus."""
    from nexus.api.events import sse_generator

    gen = sse_generator(bus, keepalive_timeout=0.05)
    # First __anext__ subscribes then waits; keepalive fires after 0.05s
    frame = await gen.__anext__()
    assert frame == ": keepalive\n\n"
    assert bus.subscriber_count == 1

    await gen.aclose()
    assert bus.subscriber_count == 0
