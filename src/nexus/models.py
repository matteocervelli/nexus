"""Pydantic shapes mirroring the Atrium schema.

These are read/write DTOs — Nexus never owns the underlying tables.
All persistence goes through Atrium HTTP endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    id: int
    type: str
    agent_role: str
    priority: Literal["P0", "P1", "P2", "P3"]
    status: Literal["pending", "running", "done", "failed"]
    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    token_cost: int = 0


class AgentRegistryEntry(BaseModel):
    id: int
    capability_class: str
    execution_backend: Literal["codex-cli", "claude-code-cli", "anthropic-sdk", "openai-sdk"]
    model: str
    profile_path: str
    tool_allowlist: list[str] = Field(default_factory=list)
    timeout_seconds: int
    monthly_token_budget: int


class BudgetLedger(BaseModel):
    id: int
    agent_id: int
    month: str  # YYYY-MM
    tokens_used: int
    tokens_budget: int

    @property
    def is_exhausted(self) -> bool:
        return self.tokens_used >= self.tokens_budget
