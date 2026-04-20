"""Budget checker — hard gate before every agent spawn.

Queries Atrium's budget_ledger and returns False when the monthly
token budget is exhausted. Fails safe on any Atrium error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class BudgetChecker:
    """Check monthly token budget before spawning an agent."""

    def __init__(self, atrium_client: httpx.AsyncClient) -> None:
        self._client = atrium_client

    async def check(self, agent_id: str, work_item_id: int | None) -> bool:
        """Return True if the agent may spawn; False if budget is exhausted.

        On any Atrium error, returns False (fail safe — never spawn blind).
        When False and work_item_id is provided, patches it to budget_blocked
        and creates a Limen notification work_item.
        """
        month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        log = logger.bind(agent_id=agent_id, work_item_id=work_item_id, month=month)

        try:
            resp = await self._client.get(
                "/budget_ledger",
                params={"agent_id": agent_id, "month": month},
            )
        except Exception as exc:
            log.error("budget.ledger_fetch_error", error=str(exc))
            return False

        if resp.status_code != 200:
            log.warning("budget.ledger_not_found", status=resp.status_code)
            return False

        ledger = resp.json()
        tokens_used: int = ledger["tokens_used"]
        pause_at: int = ledger["pause_at"]

        if tokens_used < pause_at:
            log.debug("budget.ok", tokens_used=tokens_used, pause_at=pause_at)
            return True

        log.warning("budget.exceeded", tokens_used=tokens_used, pause_at=pause_at)
        await self._handle_exceeded(agent_id=agent_id, work_item_id=work_item_id, log=log)
        return False

    async def _handle_exceeded(
        self,
        agent_id: str,
        work_item_id: int | None,
        log: Any,
    ) -> None:
        error_message = f"Monthly budget exceeded for {agent_id}"

        if work_item_id is not None:
            try:
                await self._client.patch(
                    f"/work_items/{work_item_id}",
                    json={"status": "budget_blocked", "error_message": error_message},
                )
            except Exception as exc:
                log.error("budget.patch_work_item_error", error=str(exc))

        try:
            await self._client.post(
                "/work_items",
                json={
                    "type": "notification",
                    "agent_role": "orchestrator",
                    "priority": "P1",
                    "status": "pending",
                    "context": {
                        "message": error_message,
                        "agent_id": agent_id,
                        "blocked_work_item_id": work_item_id,
                    },
                },
            )
        except Exception as exc:
            log.error("budget.notify_error", error=str(exc))
