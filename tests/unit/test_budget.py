"""Tests for BudgetChecker — TDD red phase written before implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from nexus.budget import BudgetChecker


def make_client(base_url: str = "http://localhost:8100") -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url)


def ledger_payload(tokens_used: int, pause_at: int) -> dict:
    return {"tokens_used": tokens_used, "pause_at": pause_at}


def registry_payload(agent_id: str, monthly_token_budget: int) -> dict:
    return {
        "agent_id": agent_id,
        "monthly_token_budget": monthly_token_budget,
    }


class TestBudgetCheckerUnderBudget:
    @respx.mock
    async def test_returns_true_when_under_budget(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(500, 1000))
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is True

    @respx.mock
    async def test_returns_true_at_zero_usage(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(0, 1000))
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is True


class TestBudgetCheckerOverBudget:
    @respx.mock
    async def test_returns_false_when_equal_to_budget(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(1000, 1000))
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is False

    @respx.mock
    async def test_returns_false_when_over_budget(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(1500, 1000))
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is False

    @respx.mock
    async def test_patches_work_item_when_over_budget(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(1500, 1000))
        )
        patch_route = respx.patch("http://localhost:8100/work_items/42").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(201, json={})
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            await checker.check(agent_id="agent-1", work_item_id=42)
        assert patch_route.called
        patched_body = patch_route.calls[0].request.content
        import json
        body = json.loads(patched_body)
        assert body["status"] == "budget_blocked"
        assert "agent-1" in body["error_message"]

    @respx.mock
    async def test_creates_notification_work_item_when_over_budget(self):
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(1500, 1000))
        )
        respx.patch("http://localhost:8100/work_items/42").mock(
            return_value=httpx.Response(200, json={})
        )
        notify_route = respx.post("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(201, json={})
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            await checker.check(agent_id="agent-1", work_item_id=42)
        assert notify_route.called
        import json
        body = json.loads(notify_route.calls[0].request.content)
        assert body["type"] == "notification"


class TestBudgetCheckerEdgeCases:
    @respx.mock
    async def test_ledger_not_found_returns_false(self):
        """404 from Atrium means no ledger entry — fail safe."""
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(404, json={"detail": "not found"})
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="unknown-agent", work_item_id=None)
        assert result is False

    @respx.mock
    async def test_atrium_error_returns_false(self):
        """500 from Atrium — fail safe, don't spawn."""
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(500, json={"detail": "internal error"})
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is False

    @respx.mock
    async def test_no_work_item_id_skips_patch(self):
        """When work_item_id is None, no PATCH is sent even when over budget."""
        respx.get("http://localhost:8100/budget_ledger").mock(
            return_value=httpx.Response(200, json=ledger_payload(2000, 1000))
        )
        notify_route = respx.post("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(201, json={})
        )
        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            checker = BudgetChecker(atrium_client=client)
            result = await checker.check(agent_id="agent-1", work_item_id=None)
        assert result is False
        # notification still fires even without a work_item_id
        assert notify_route.called
