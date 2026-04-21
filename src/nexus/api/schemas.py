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
    name: str
    status: str
    step_index: int
    depends_on: list[str] = []
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
