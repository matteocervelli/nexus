"""Nexus scheduler — polls pending work_items and dispatches to adapters.

Single responsibility: one tick() per heartbeat. No state between ticks.
All persistence goes through Atrium HTTP; no local state.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from nexus.adapter_base import AdapterRequest, AdapterResult
from nexus.adapters import ADAPTER_REGISTRY
from nexus.budget import BudgetChecker
from nexus.models import AgentRegistryEntry, WorkflowStep, WorkItem

logger = structlog.get_logger(__name__)

_POLL_LIMIT = 5
_ADAPTER_TIMEOUT_BUFFER = 30


class Scheduler:
    """Single-tick scheduler: poll → ready-check → budget-check → dispatch."""

    def __init__(
        self,
        atrium_client: httpx.AsyncClient,
        budget_checker: BudgetChecker,
    ) -> None:
        self._client = atrium_client
        self._budget = budget_checker

    async def tick(self) -> None:
        """Single heartbeat tick: poll pending work_items, dispatch ready ones."""
        items = await self._poll_pending()
        for item in items:
            steps = await self._fetch_steps(item)
            if not self._is_ready(item, steps):
                logger.debug("scheduler.item_not_ready", work_item_id=str(item.id))
                continue
            allowed = await self._budget.check(item.agent_role, item.id)
            if not allowed:
                logger.info("scheduler.budget_blocked", work_item_id=str(item.id))
                continue
            await self._dispatch(item)

    async def _poll_pending(self) -> list[WorkItem]:
        try:
            resp = await self._client.get(
                "/api/work_items",
                params={"status": "pending", "limit": _POLL_LIMIT},
            )
            resp.raise_for_status()
            return [WorkItem.model_validate(r) for r in resp.json()]
        except Exception as exc:
            logger.error("scheduler.poll_error", error=str(exc))
            return []

    async def _fetch_steps(self, item: WorkItem) -> list[WorkflowStep]:
        workflow_id = item.context.get("workflow_id")
        if not workflow_id:
            return []
        try:
            resp = await self._client.get(
                "/api/workflow_steps",
                params={"workflow_id": workflow_id},
            )
            if resp.status_code == 200:
                return [WorkflowStep.model_validate(s) for s in resp.json()]
        except Exception as exc:
            logger.warning("scheduler.fetch_steps_error", error=str(exc))
        return []

    def _is_ready(self, item: WorkItem, steps: list[WorkflowStep]) -> bool:
        """Return True if all dependencies are satisfied."""
        workflow_id = item.context.get("workflow_id")
        if not workflow_id:
            return True

        depends_on: list[str] = item.context.get("depends_on", [])
        if not depends_on:
            return True

        steps_by_id = {str(s.id): s for s in steps}
        for dep_id in depends_on:
            dep = steps_by_id.get(dep_id)
            if dep is None or dep.status != "done":
                return False

        condition = item.context.get("condition")
        if condition:
            return self._eval_condition(condition, item)

        return True

    def _eval_condition(self, condition: str, item: WorkItem) -> bool:
        """Evaluate simple DSL: 'field.operator.value' e.g. 'result.confidence.gte.0.8'."""
        parts = condition.split(".")
        if len(parts) < 3:
            raise NotImplementedError(f"Unsupported condition DSL: {condition!r}")

        # field may be nested: result.confidence → parts[0]="result", then operator
        # Format: <top_field>.<sub_field?>.<operator>.<value>
        # We support exactly: field.operator.value (3 parts) or field.subfield.operator.value (4 parts)
        if len(parts) == 3:
            field, operator, raw_value = parts
            data = item.context.get(field)
        elif len(parts) == 4:
            field, subfield, operator, raw_value = parts
            top = item.context.get(field, {})
            data = top.get(subfield) if isinstance(top, dict) else None
        else:
            raise NotImplementedError(f"Unsupported condition DSL: {condition!r}")

        try:
            value = float(raw_value) if raw_value is not None else 0.0
            data = float(data) if data is not None else 0.0
        except (TypeError, ValueError):
            pass

        if operator == "eq":
            return data == value
        if operator == "gte":
            return data >= value  # type: ignore[operator]
        if operator == "lte":
            return data <= value  # type: ignore[operator]
        raise NotImplementedError(f"Unsupported condition operator: {operator!r}")

    async def _dispatch(self, item: WorkItem) -> None:
        log = logger.bind(work_item_id=str(item.id), agent_role=item.agent_role)
        try:
            entry = await self._fetch_registry_entry(item.agent_role)
            if entry is None:
                await self._patch_failed(item.id, "Agent registry entry not found")
                return

            await self._patch_item(item.id, {"status": "running", "started_at": _now_iso()})

            adapter_cls = ADAPTER_REGISTRY[entry.execution_backend]
            adapter = adapter_cls()
            request = _build_request(item, entry)

            timeout = entry.timeout_seconds + _ADAPTER_TIMEOUT_BUFFER
            result: AdapterResult = await asyncio.wait_for(
                adapter.invoke_heartbeat(request),
                timeout=timeout,
            )

            work_item_status = "done" if result.status == "succeeded" else "failed"
            patch_body: dict[str, Any] = {
                "status": work_item_status,
                "completed_at": _now_iso(),
                "result": {
                    "adapter_status": result.status,
                    "stdout": result.stdout_excerpt,
                    "payload": result.result_payload,
                },
            }
            if result.usage:
                patch_body["token_cost"] = result.usage.tokens_used

            await self._patch_item(item.id, patch_body)
            log.info("scheduler.dispatch_complete", adapter_status=result.status)

        except Exception as exc:
            log.error("scheduler.dispatch_error", error=str(exc))
            await self._patch_failed(item.id, str(exc))

    async def _fetch_registry_entry(self, agent_role: str) -> AgentRegistryEntry | None:
        try:
            resp = await self._client.get(f"/api/agent_registry/{agent_role}")
            if resp.status_code == 200:
                return AgentRegistryEntry.model_validate(resp.json())
            logger.error(
                "scheduler.registry_not_found", agent_role=agent_role, status=resp.status_code
            )
        except Exception as exc:
            logger.error("scheduler.registry_fetch_error", error=str(exc))
        return None

    async def _patch_item(self, item_id: uuid.UUID, body: dict[str, Any]) -> None:
        try:
            resp = await self._client.patch(f"/api/work_items/{item_id}", json=body)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("scheduler.patch_error", work_item_id=str(item_id), error=str(exc))

    async def _patch_failed(self, item_id: uuid.UUID, reason: str) -> None:
        await self._patch_item(
            item_id,
            {"status": "failed", "result": {"error": reason}, "completed_at": _now_iso()},
        )


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _build_request(item: WorkItem, entry: AgentRegistryEntry) -> AdapterRequest:
    # work_item_id in AdapterRequest is int; use deterministic hash of UUID
    work_item_int = int(item.id) % (2**31)
    return AdapterRequest(
        agent_id=str(entry.id),
        agent_profile=entry.profile_path,
        work_item_id=work_item_int,
        work_type=item.type,
        priority=item.priority,
        prompt_context=json.dumps(item.context),
        timeout_seconds=entry.timeout_seconds,
        correlation_id=str(item.id),
        tools_allowlist=entry.tool_allowlist,
        extra={
            "model": entry.model,
            "max_turns": entry.max_turns if entry.max_turns is not None else 80,
        },
    )
