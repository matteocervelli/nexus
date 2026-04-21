"""End-to-end integration test: Code Agent work_item lifecycle.

Requires a live Atrium instance at $ATRIUM_URL (default http://localhost:8100).
Skip with: pytest -m "not integration"

Run locally:
    cd /data/dev/services/nexus
    ATRIUM_URL=http://localhost:8100 uv run pytest tests/test_integration/ -v -m integration
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx
import pytest

from nexus.models import WorkItem, WorkItemCreate

ATRIUM_URL = os.environ.get("ATRIUM_URL", "http://localhost:8100")
pytestmark = pytest.mark.integration


@pytest.fixture
async def atrium() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=ATRIUM_URL, timeout=10) as client:
        yield client


@pytest.fixture
async def test_work_item(atrium: httpx.AsyncClient) -> WorkItem:
    """Create a code-search work_item and clean it up after the test."""
    payload = WorkItemCreate(
        type="code-search",
        agent_role="code-agent",
        priority="P2",
        context={"repo": "limen-assistant", "query": "TODOs"},
    )
    resp = await atrium.post("/api/work_items", json=payload.model_dump())
    assert resp.status_code == 201, f"create failed: {resp.text}"
    item = WorkItem.model_validate(resp.json())

    yield item

    # Cleanup: mark done so it doesn't linger as pending
    await atrium.patch(
        f"/api/work_items/{item.id}",
        json={"status": "done", "result": {"cleanup": "test teardown"}},
    )


async def test_work_item_create_and_read(atrium: httpx.AsyncClient, test_work_item: WorkItem):
    """Work item round-trips through Atrium with correct shape."""
    resp = await atrium.get(f"/api/work_items/{test_work_item.id}")
    assert resp.status_code == 200
    fetched = WorkItem.model_validate(resp.json())
    assert fetched.id == test_work_item.id
    assert fetched.type == "code-search"
    assert fetched.agent_role == "code-agent"
    assert fetched.status == "pending"
    assert fetched.context == {"repo": "limen-assistant", "query": "TODOs"}


async def test_work_item_status_transition(atrium: httpx.AsyncClient, test_work_item: WorkItem):
    """Work item can be transitioned through pending → running → done."""
    now = datetime.now(tz=UTC).isoformat()

    resp = await atrium.patch(
        f"/api/work_items/{test_work_item.id}",
        json={"status": "running", "started_at": now},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    result = {"issues_found": 3, "files": ["src/limen/bot.py", "src/limen/core.py"]}
    resp = await atrium.patch(
        f"/api/work_items/{test_work_item.id}",
        json={"status": "done", "result": result, "token_cost": 500},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["result"]["issues_found"] == 3
    assert body["token_cost"] == 500


async def test_scheduler_poll_sees_pending_item(
    atrium: httpx.AsyncClient, test_work_item: WorkItem
):
    """Scheduler poll endpoint returns the pending item in list."""
    resp = await atrium.get("/api/work_items", params={"status": "pending", "limit": 100})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert str(test_work_item.id) in ids, "Created work_item not visible to scheduler poll"
