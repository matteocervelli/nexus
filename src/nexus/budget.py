"""Budget checker — hard gate before every agent spawn.

Two-step check:
  1. GET /api/budget_ledger?agent_role=&year_month= → tokens_consumed + paused_at
  2. GET /api/agent_registry/{agent_role} → monthly_token_budget

404 on ledger means no usage this month → allow spawn.
Any Atrium error → fail safe (block spawn, never proceed blind).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from nexus.models import AgentRegistryEntry, BudgetLedger

logger = structlog.get_logger(__name__)


class BudgetChecker:
    """Check monthly token budget before spawning an agent."""

    def __init__(self, atrium_client: httpx.AsyncClient) -> None:
        self._client = atrium_client

    async def check(self, agent_role: str, work_item_id: uuid.UUID | None = None) -> bool:
        """Return True if the agent may spawn; False if budget is exhausted or paused.

        On any Atrium error, returns False (fail safe — never spawn blind).
        When False and work_item_id is provided, patches work_item to failed
        and creates a Limen notification work_item.
        """
        year_month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        log = logger.bind(agent_role=agent_role, work_item_id=str(work_item_id), year_month=year_month)

        # Step 1: get current usage
        try:
            ledger_resp = await self._client.get(
                "/api/budget_ledger",
                params={"agent_role": agent_role, "year_month": year_month},
            )
        except Exception as exc:
            log.error("budget.ledger_fetch_error", error=str(exc))
            return False

        if ledger_resp.status_code == 404:
            # No usage this month → allow spawn
            log.debug("budget.no_usage_yet")
            return True

        if ledger_resp.status_code != 200:
            log.error("budget.ledger_unexpected_status", status=ledger_resp.status_code)
            return False

        try:
            ledger = BudgetLedger.model_validate(ledger_resp.json())
        except Exception as exc:
            log.error("budget.ledger_parse_error", error=str(exc))
            return False

        if ledger.is_paused:
            log.warning("budget.agent_paused", paused_at=str(ledger.paused_at))
            await self._handle_exceeded(agent_role=agent_role, work_item_id=work_item_id, log=log)
            return False

        # Step 2: get budget cap from agent registry
        try:
            agent_resp = await self._client.get(f"/api/agent_registry/{agent_role}")
        except Exception as exc:
            log.error("budget.registry_fetch_error", error=str(exc))
            return False

        if agent_resp.status_code != 200:
            log.error("budget.registry_not_found", status=agent_resp.status_code)
            return False

        try:
            agent = AgentRegistryEntry.model_validate(agent_resp.json())
        except Exception as exc:
            log.error("budget.registry_parse_error", error=str(exc))
            return False

        if ledger.is_over_budget(agent.monthly_token_budget):
            log.warning(
                "budget.exceeded",
                tokens_consumed=ledger.tokens_consumed,
                monthly_token_budget=agent.monthly_token_budget,
            )
            await self._handle_exceeded(agent_role=agent_role, work_item_id=work_item_id, log=log)
            return False

        log.debug(
            "budget.ok",
            tokens_consumed=ledger.tokens_consumed,
            monthly_token_budget=agent.monthly_token_budget,
        )
        return True

    async def _handle_exceeded(
        self,
        agent_role: str,
        work_item_id: uuid.UUID | None,
        log: Any,
    ) -> None:
        error_message = f"Monthly token budget exceeded or agent paused: {agent_role}"

        if work_item_id is not None:
            try:
                await self._client.patch(
                    f"/api/work_items/{work_item_id}",
                    json={"status": "failed", "result": {"error": error_message}},
                )
            except Exception as exc:
                log.error("budget.patch_work_item_error", error=str(exc))

        try:
            await self._client.post(
                "/api/work_items",
                json={
                    "type": "notification",
                    "agent_role": "orchestrator",
                    "priority": "P1",
                    "context": {
                        "message": error_message,
                        "blocked_agent_role": agent_role,
                        "blocked_work_item_id": str(work_item_id) if work_item_id else None,
                    },
                },
            )
        except Exception as exc:
            log.error("budget.notify_error", error=str(exc))
