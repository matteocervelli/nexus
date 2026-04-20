"""Pydantic shapes mirroring the Atrium schema.

These are read/write DTOs — Nexus never owns the underlying tables.
All persistence goes through Atrium HTTP endpoints.

Field names, types, and optionality MUST stay in sync with Atrium's Pydantic schemas
in /data/dev/services/atrium/backend/app/schemas/. Atrium uses UUID PKs for all
Nexus-domain tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    id: uuid.UUID
    type: str
    agent_role: str
    priority: Literal["P0", "P1", "P2", "P3"]
    status: Literal["pending", "running", "done", "failed"]
    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    token_cost: int = 0


class WorkItemCreate(BaseModel):
    type: str
    agent_role: str
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    context: dict[str, Any] = Field(default_factory=dict)


class WorkItemUpdate(BaseModel):
    status: Literal["pending", "running", "done", "failed"] | None = None
    result: dict[str, Any] | None = None
    token_cost: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentRegistryEntry(BaseModel):
    id: uuid.UUID
    agent_role: str
    capability_class: str
    execution_backend: Literal["codex-cli", "claude-code-cli", "anthropic-sdk", "openai-sdk"]
    model: str
    profile_path: str
    tool_allowlist: list[str] = Field(default_factory=list)
    timeout_seconds: int
    monthly_token_budget: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime | None = None


class BudgetLedger(BaseModel):
    id: uuid.UUID
    agent_role: str
    year_month: date
    tokens_consumed: int
    cost_usd: float
    run_count: int
    paused_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    def is_over_budget(self, monthly_token_budget: int) -> bool:
        return self.tokens_consumed >= monthly_token_budget

    @property
    def is_paused(self) -> bool:
        return self.paused_at is not None


class WorkflowStep(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    step_index: int
    agent_role: str
    depends_on: list[Any] = Field(default_factory=list)
    condition: str | None = None
    execution_backend: str
    model: str
    prompt_context: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CostEventCreate(BaseModel):
    agent_role: str
    work_item_id: uuid.UUID | None = None
    workflow_step_id: uuid.UUID | None = None
    execution_backend: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    cost_source: Literal["exact", "estimated"] = "estimated"
    year_month: date
    occurred_at: datetime
