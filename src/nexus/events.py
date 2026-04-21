"""Internal event bus for broadcasting lifecycle events to SSE subscribers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class EventType(StrEnum):
    WORK_ITEM_STATUS_CHANGED = "work_item_status_changed"
    WORKFLOW_STEP_UPDATED = "workflow_step_updated"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETED = "agent_completed"
    BUDGET_ALERT = "budget_alert"


class EventBus:
    """Fan-out pub/sub bus; one asyncio.Queue per SSE subscriber.

    Queues are bounded — events are dropped (never block) when a slow consumer
    falls behind. The SSE generator handles disconnect cleanup via unsubscribe().
    """

    def __init__(self, queue_maxsize: int = 100) -> None:
        self._queue_maxsize = queue_maxsize
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(q)

    async def publish(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Publish an event to all active subscribers.

        Never blocks — drops events to full queues with a warning.
        """
        event = {
            "type": event_type.value,
            "data": data,
            "ts": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        }
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("event_bus.queue_full_drop", event_type=event_type.value)
