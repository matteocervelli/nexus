"""Unit tests for Scheduler — red phase."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from nexus.budget import BudgetChecker
from nexus.models import WorkItem

_BASE = "http://localhost:8100"
_AGENT_ROLE = "code-agent"
_ITEM_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_AGENT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


def _work_item(status: str = "pending", workflow_id: str | None = None) -> dict:
    ctx: dict = {}
    if workflow_id:
        ctx["workflow_id"] = workflow_id
    return {
        "id": str(_ITEM_ID),
        "type": "code_task",
        "agent_role": _AGENT_ROLE,
        "priority": "P2",
        "status": status,
        "context": ctx,
        "result": None,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "updated_at": None,
        "started_at": None,
        "completed_at": None,
        "token_cost": 0,
    }


def _agent_entry() -> dict:
    return {
        "id": str(_AGENT_ID),
        "agent_role": _AGENT_ROLE,
        "capability_class": "code",
        "execution_backend": "claude-code-cli",
        "model": "claude-sonnet-4-6",
        "profile_path": "agents/code-agent/CLAUDE.md",
        "tool_allowlist": [],
        "timeout_seconds": 300,
        "monthly_token_budget": 100000,
        "is_active": True,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "updated_at": None,
    }


@respx.mock
@pytest.mark.asyncio
async def test_tick_dispatches_pending_item():
    """Happy path: pending item → running → done."""
    from nexus.adapter_base import AdapterResult
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent_entry())
    )
    running_patch = respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("running"))
    )

    fake_result = AdapterResult(
        status="succeeded",
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
    )

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with (
            patch.object(checker, "check", new=AsyncMock(return_value=True)),
            patch("nexus.scheduler.ADAPTER_REGISTRY") as mock_registry,
        ):
            mock_adapter = AsyncMock()
            mock_adapter.invoke_heartbeat = AsyncMock(return_value=fake_result)
            mock_registry.__getitem__ = MagicMock(return_value=lambda: mock_adapter)

            scheduler = Scheduler(client, checker)
            await scheduler.tick()

    assert running_patch.called
    calls = running_patch.calls
    bodies = [c.request.content for c in calls]
    assert any(b"running" in b for b in bodies)
    assert any(b"done" in b for b in bodies)


@respx.mock
@pytest.mark.asyncio
async def test_budget_blocked_skips_dispatch():
    """BudgetChecker.check returns False → item never patched to running."""
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("failed"))
    )

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with patch.object(checker, "check", new=AsyncMock(return_value=False)):
            scheduler = Scheduler(client, checker)
            await scheduler.tick()

    # BudgetChecker.check(False) handles its own patch; scheduler should NOT touch it
    for call in patch_route.calls:
        body = call.request.content.decode()
        assert "running" not in body


@respx.mock
@pytest.mark.asyncio
async def test_adapter_failure_maps_to_failed():
    """AdapterResult(status='timed_out') → work_item PATCH status=failed."""
    from nexus.adapter_base import AdapterResult
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent_entry())
    )
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("failed"))
    )

    fake_result = AdapterResult(
        status="timed_out",
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
    )

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with (
            patch.object(checker, "check", new=AsyncMock(return_value=True)),
            patch("nexus.scheduler.ADAPTER_REGISTRY") as mock_registry,
        ):
            mock_adapter = AsyncMock()
            mock_adapter.invoke_heartbeat = AsyncMock(return_value=fake_result)
            mock_registry.__getitem__ = MagicMock(return_value=lambda: mock_adapter)

            scheduler = Scheduler(client, checker)
            await scheduler.tick()

    last_call = patch_route.calls[-1]
    import json as _json

    body = _json.loads(last_call.request.content)
    assert body["status"] == "failed"


@pytest.mark.asyncio
async def test_item_with_no_workflow_id_is_always_ready():
    """WorkItem with no workflow_id in context → _is_ready returns True."""
    from nexus.scheduler import Scheduler

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        scheduler = Scheduler(client, checker)

    item = WorkItem(
        id=_ITEM_ID,
        type="code_task",
        agent_role=_AGENT_ROLE,
        priority="P2",
        status="pending",
        context={},
        created_at=datetime.now(tz=UTC),
    )
    assert scheduler._is_ready(item, []) is True


@pytest.mark.asyncio
async def test_depends_on_not_done_blocks_item():
    """WorkflowStep with status != done → _is_ready returns False."""
    from nexus.models import WorkflowStep
    from nexus.scheduler import Scheduler

    step_id = uuid.UUID("cccccccc-0000-0000-0000-000000000003")

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        scheduler = Scheduler(client, checker)

    item = WorkItem(
        id=_ITEM_ID,
        type="code_task",
        agent_role=_AGENT_ROLE,
        priority="P2",
        status="pending",
        context={"workflow_id": str(uuid.uuid4()), "depends_on": [str(step_id)]},
        created_at=datetime.now(tz=UTC),
    )
    step = WorkflowStep(
        id=step_id,
        workflow_id=uuid.uuid4(),
        step_index=0,
        agent_role=_AGENT_ROLE,
        depends_on=[],
        condition=None,
        execution_backend="claude-code-cli",
        model="claude-sonnet-4-6",
        prompt_context={},
        status="running",
        created_at=datetime.now(tz=UTC),
    )
    assert scheduler._is_ready(item, [step]) is False


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_exception_patches_to_failed():
    """Adapter raises exception → item PATCH to failed."""
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent_entry())
    )
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("failed"))
    )

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with (
            patch.object(checker, "check", new=AsyncMock(return_value=True)),
            patch("nexus.scheduler.ADAPTER_REGISTRY") as mock_registry,
        ):
            mock_adapter = AsyncMock()
            mock_adapter.invoke_heartbeat = AsyncMock(side_effect=RuntimeError("adapter boom"))
            mock_registry.__getitem__ = MagicMock(return_value=lambda: mock_adapter)

            scheduler = Scheduler(client, checker)
            await scheduler.tick()

    import json as _json

    last_body = _json.loads(patch_route.calls[-1].request.content)
    assert last_body["status"] == "failed"
    assert "error" in last_body.get("result", {})


def test_build_request_plumbs_model_tools_max_turns():
    """_build_request forwards model, tool_allowlist, and max_turns from registry entry."""
    from datetime import UTC, datetime

    from nexus.models import AgentRegistryEntry, WorkItem
    from nexus.scheduler import _build_request

    entry = AgentRegistryEntry(
        id=_AGENT_ID,
        agent_role=_AGENT_ROLE,
        capability_class="code",
        execution_backend="claude-code-cli",
        model="claude-opus-4-7",
        profile_path="agents/code-agent/CLAUDE.md",
        tool_allowlist=["Read", "Bash"],
        timeout_seconds=300,
        monthly_token_budget=100000,
        is_active=True,
        created_at=datetime.now(tz=UTC),
        max_turns=80,
    )

    item = WorkItem(
        id=_ITEM_ID,
        type="code_task",
        agent_role=_AGENT_ROLE,
        priority="P2",
        status="pending",
        context={"task": "do something"},
        created_at=datetime.now(tz=UTC),
    )

    request = _build_request(item, entry)

    assert request.extra.get("model") == "claude-opus-4-7"
    assert request.extra.get("max_turns") == 80
    assert request.tools_allowlist == ["Read", "Bash"]


def test_build_request_max_turns_defaults_to_80_when_none():
    """When entry.max_turns is None, extra['max_turns'] defaults to 80."""
    from datetime import UTC, datetime

    from nexus.models import AgentRegistryEntry, WorkItem
    from nexus.scheduler import _build_request

    entry = AgentRegistryEntry(
        id=_AGENT_ID,
        agent_role=_AGENT_ROLE,
        capability_class="code",
        execution_backend="claude-code-cli",
        model="claude-sonnet-4-6",
        profile_path="agents/code-agent/CLAUDE.md",
        tool_allowlist=[],
        timeout_seconds=300,
        monthly_token_budget=100000,
        is_active=True,
        created_at=datetime.now(tz=UTC),
        max_turns=None,
    )

    item = WorkItem(
        id=_ITEM_ID,
        type="code_task",
        agent_role=_AGENT_ROLE,
        priority="P2",
        status="pending",
        context={},
        created_at=datetime.now(tz=UTC),
    )

    request = _build_request(item, entry)
    assert request.extra.get("max_turns") == 80


# ---------------------------------------------------------------------------
# Event bus integration
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_publishes_agent_spawned_and_completed():
    """Scheduler publishes AGENT_SPAWNED on pending→running and AGENT_COMPLETED on done."""
    from nexus.adapter_base import AdapterResult
    from nexus.events import EventBus, EventType
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent_entry())
    )
    respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("done"))
    )

    fake_result = AdapterResult(
        status="succeeded",
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
    )

    bus = EventBus()
    q = bus.subscribe()

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with (
            patch.object(checker, "check", new=AsyncMock(return_value=True)),
            patch("nexus.scheduler.ADAPTER_REGISTRY") as mock_registry,
        ):
            mock_adapter = AsyncMock()
            mock_adapter.invoke_heartbeat = AsyncMock(return_value=fake_result)
            mock_registry.__getitem__ = MagicMock(return_value=lambda: mock_adapter)

            scheduler = Scheduler(client, checker, event_bus=bus)
            await scheduler.tick()

    event_types = []
    while not q.empty():
        event_types.append(q.get_nowait()["type"])

    assert EventType.AGENT_SPAWNED.value in event_types
    assert EventType.AGENT_COMPLETED.value in event_types
    assert EventType.WORK_ITEM_STATUS_CHANGED.value in event_types


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_exception_publishes_agent_completed_failed():
    """Adapter exception → AGENT_COMPLETED event with status=failed."""
    from nexus.events import EventBus, EventType
    from nexus.scheduler import Scheduler

    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[_work_item()]))
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent_entry())
    )
    respx.patch(f"{_BASE}/api/work_items/{_ITEM_ID}").mock(
        return_value=httpx.Response(200, json=_work_item("failed"))
    )

    bus = EventBus()
    q = bus.subscribe()

    async with httpx.AsyncClient(base_url=_BASE) as client:
        checker = BudgetChecker(client)
        with (
            patch.object(checker, "check", new=AsyncMock(return_value=True)),
            patch("nexus.scheduler.ADAPTER_REGISTRY") as mock_registry,
        ):
            mock_adapter = AsyncMock()
            mock_adapter.invoke_heartbeat = AsyncMock(side_effect=RuntimeError("boom"))
            mock_registry.__getitem__ = MagicMock(return_value=lambda: mock_adapter)

            scheduler = Scheduler(client, checker, event_bus=bus)
            await scheduler.tick()

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    completed_events = [e for e in events if e["type"] == EventType.AGENT_COMPLETED.value]
    assert len(completed_events) >= 1
    assert completed_events[0]["data"]["status"] == "failed"
