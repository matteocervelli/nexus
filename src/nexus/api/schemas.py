"""Pydantic response models for the Nexus dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class WorkflowSummary(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowStep(BaseModel):
    id: str
    step_index: int
    agent_role: str
    status: str
    depends_on: list[Any] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowDetail(WorkflowSummary):
    dag: dict[str, Any] = {}
    updated_at: datetime | None = None
    steps: list[WorkflowStep] = []


class AgentStatus(BaseModel):
    agent_role: str
    execution_backend: str
    model: str
    running_work_items: int
    monthly_token_budget: int
    tokens_used_this_month: int


class BudgetAlert(BaseModel):
    agent_role: str
    tokens_used: int
    monthly_budget: int
    percent: float


class StatusSummary(BaseModel):
    running_count: int
    queue_depth: int
    budget_alerts: list[BudgetAlert] = []


class CancelAction(BaseModel):
    action: Literal["cancel"]


class WorkItemSummary(BaseModel):
    id: str
    type: str
    agent_role: str
    priority: str
    status: str
    context: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    token_cost: int
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunSummary(BaseModel):
    id: str
    work_item_id: str | None = None
    workflow_step_id: str | None = None
    agent_role: str
    execution_backend: str
    model: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    tokens_total: int | None = None
    cost_usd: float | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RunDetail(RunSummary):
    external_run_id: str | None = None
    session_kind: str | None = None
    session_id_before: str | None = None
    session_id_after: str | None = None
    session_metadata: dict[str, Any] | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    cost_source: str | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    result_payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class RunEvent(BaseModel):
    id: str
    run_id: str
    event_index: int
    event_type: str
    tool_name: str | None = None
    payload: dict[str, Any] = {}
    occurred_at: datetime
    created_at: datetime
