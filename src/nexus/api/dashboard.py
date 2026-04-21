"""Dashboard API router — proxies to Atrium for workflow, agent, and status data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from nexus.api.deps import get_atrium_client
from nexus.api.schemas import (
    AgentStatus,
    BudgetAlert,
    CancelAction,
    StatusSummary,
    WorkflowDetail,
    WorkflowSummary,
)

router = APIRouter(prefix="/nexus/api", tags=["dashboard"])


def _raise_for_atrium(exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found")
    raise HTTPException(status_code=502, detail="Upstream error")


@router.get("/workflows", response_model=list[WorkflowSummary])
async def list_workflows(
    status: str | None = Query(None),
    limit: int | None = Query(None),
    offset: int | None = Query(None),
    client: httpx.AsyncClient = Depends(get_atrium_client),
) -> Any:
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = status
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    try:
        resp = await client.get("/api/workflows", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)
    return resp.json()


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    workflow_id: str,
    client: httpx.AsyncClient = Depends(get_atrium_client),
) -> Any:
    try:
        resp = await client.get(f"/api/workflows/{workflow_id}")
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)
    return resp.json()


@router.patch("/workflows/{workflow_id}", response_model=WorkflowSummary)
async def cancel_workflow(
    workflow_id: str,
    body: CancelAction,
    client: httpx.AsyncClient = Depends(get_atrium_client),
) -> Any:
    try:
        resp = await client.patch(f"/api/workflows/{workflow_id}", json={"status": "cancelled"})
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)
    return resp.json()


@router.get("/agents", response_model=list[AgentStatus])
async def list_agents(
    client: httpx.AsyncClient = Depends(get_atrium_client),
) -> Any:
    try:
        agents_resp = await client.get("/api/agent_registry")
        agents_resp.raise_for_status()
        agents: list[dict[str, Any]] = agents_resp.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)

    try:
        running_resp = await client.get(
            "/api/work_items", params={"status": "running", "limit": 1000}
        )
        running_resp.raise_for_status()
        running_items: list[dict[str, Any]] = running_resp.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)

    running_count: dict[str, int] = {}
    for item in running_items:
        role = item["agent_role"]
        running_count[role] = running_count.get(role, 0) + 1

    year_month = datetime.now().strftime("%Y-%m")
    result: list[AgentStatus] = []
    for agent in agents:
        role = agent["agent_role"]
        try:
            ledger_resp = await client.get(
                "/api/budget_ledger", params={"agent_role": role, "year_month": year_month}
            )
            ledger_resp.raise_for_status()
            tokens_used = ledger_resp.json().get("tokens_consumed", 0)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                tokens_used = 0
            else:
                _raise_for_atrium(exc)

        result.append(
            AgentStatus(
                agent_role=role,
                execution_backend=agent.get("execution_backend", ""),
                model=agent.get("model", ""),
                running_work_items=running_count.get(role, 0),
                monthly_token_budget=agent.get("monthly_token_budget", 0),
                tokens_used_this_month=tokens_used,
            )
        )
    return result


@router.get("/status", response_model=StatusSummary)
async def get_status(
    client: httpx.AsyncClient = Depends(get_atrium_client),
) -> Any:
    try:
        running_resp = await client.get("/api/work_items", params={"status": "running"})
        running_resp.raise_for_status()
        running_items: list[dict[str, Any]] = running_resp.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)

    try:
        pending_resp = await client.get("/api/work_items", params={"status": "pending"})
        pending_resp.raise_for_status()
        pending_items: list[dict[str, Any]] = pending_resp.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)

    try:
        agents_resp = await client.get("/api/agent_registry")
        agents_resp.raise_for_status()
        agents: list[dict[str, Any]] = agents_resp.json()
    except httpx.HTTPStatusError as exc:
        _raise_for_atrium(exc)

    year_month = datetime.now().strftime("%Y-%m")
    budget_alerts: list[BudgetAlert] = []
    for agent in agents:
        budget = agent.get("monthly_token_budget", 0)
        if budget <= 0:
            continue
        role = agent["agent_role"]
        try:
            ledger_resp = await client.get(
                "/api/budget_ledger", params={"agent_role": role, "year_month": year_month}
            )
            ledger_resp.raise_for_status()
            tokens_used = ledger_resp.json().get("tokens_consumed", 0)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            _raise_for_atrium(exc)

        ratio = tokens_used / budget
        if ratio >= 0.8:
            budget_alerts.append(
                BudgetAlert(
                    agent_role=role,
                    tokens_used=tokens_used,
                    monthly_budget=budget,
                    percent=round(ratio * 100, 1),
                )
            )

    return StatusSummary(
        running_count=len(running_items),
        queue_depth=len(pending_items),
        budget_alerts=budget_alerts,
    )
