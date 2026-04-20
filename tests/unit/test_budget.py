"""Unit tests for BudgetChecker."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from nexus.budget import BudgetChecker

_BASE = "http://localhost:8100"
_AGENT_ROLE = "code-agent"
_WORK_ITEM_ID = uuid.UUID("00000000-0000-0000-0000-000000000042")


def _ledger(tokens_consumed: int, paused_at: datetime | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "agent_role": _AGENT_ROLE,
        "year_month": str(date.today().replace(day=1)),
        "tokens_consumed": tokens_consumed,
        "cost_usd": 0.0,
        "run_count": 1,
        "paused_at": paused_at.isoformat() if paused_at else None,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "updated_at": None,
    }


def _agent(monthly_token_budget: int = 10000) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "agent_role": _AGENT_ROLE,
        "capability_class": "code",
        "execution_backend": "claude-code-cli",
        "model": "claude-sonnet-4-6",
        "profile_path": "agents/code-agent/CLAUDE.md",
        "tool_allowlist": [],
        "timeout_seconds": 300,
        "monthly_token_budget": monthly_token_budget,
        "is_active": True,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "updated_at": None,
    }


@respx.mock
async def test_under_budget_returns_true():
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(200, json=_ledger(500))
    )
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent(10000))
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE) is True


@respx.mock
async def test_over_budget_returns_false():
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(200, json=_ledger(10000))
    )
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent(10000))
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE) is False


@respx.mock
async def test_no_ledger_row_allows_spawn():
    """404 on ledger = no usage this month → allow."""
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE) is True


@respx.mock
async def test_paused_agent_returns_false():
    paused = datetime.now(tz=timezone.utc)
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(200, json=_ledger(0, paused_at=paused))
    )
    respx.patch(f"{_BASE}/api/work_items/{_WORK_ITEM_ID}").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(f"{_BASE}/api/work_items").mock(
        return_value=httpx.Response(201, json={})
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE, _WORK_ITEM_ID) is False


@respx.mock
async def test_atrium_network_error_returns_false():
    respx.get(f"{_BASE}/api/budget_ledger").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE) is False


@respx.mock
async def test_over_budget_patches_work_item():
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(200, json=_ledger(15000))
    )
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(200, json=_agent(10000))
    )
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_WORK_ITEM_ID}").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post(f"{_BASE}/api/work_items").mock(
        return_value=httpx.Response(201, json={})
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        result = await BudgetChecker(client).check(_AGENT_ROLE, _WORK_ITEM_ID)

    assert result is False
    assert patch_route.called
    patched_body = patch_route.calls[0].request.content
    import json
    body = json.loads(patched_body)
    assert body["status"] == "failed"


@respx.mock
async def test_registry_404_returns_false():
    respx.get(f"{_BASE}/api/budget_ledger").mock(
        return_value=httpx.Response(200, json=_ledger(500))
    )
    respx.get(f"{_BASE}/api/agent_registry/{_AGENT_ROLE}").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    async with httpx.AsyncClient(base_url=_BASE) as client:
        assert await BudgetChecker(client).check(_AGENT_ROLE) is False
