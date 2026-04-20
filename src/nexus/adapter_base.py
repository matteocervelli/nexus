"""Common runtime adapter contract for Nexus.

Every execution backend (claude-code-cli, codex-cli, process, http) must
implement AdapterBase. Nexus Core talks only to this interface.

See: docs/adr/0003-runtime-adapter-contract.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SessionMode(StrEnum):
    EPHEMERAL = "ephemeral"
    RESUMABLE = "resumable"


# ---------------------------------------------------------------------------
# Supporting return types
# ---------------------------------------------------------------------------


class AdapterDescription(BaseModel):
    model_config = ConfigDict(frozen=True)

    adapter_id: str
    execution_mode: str  # e.g. "subprocess", "http"
    session_mode: SessionMode
    capabilities: list[str]


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    errors: list[str] = Field(default_factory=list)


class UsageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    tokens_used: int
    cost_usd: float
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Adapter I/O models
# ---------------------------------------------------------------------------


AdapterStatus = Literal[
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
    "budget_blocked",
    "environment_error",
]


class AdapterRequest(BaseModel):
    """Normalized input for every adapter invocation (ADR-0003 §Standard Input)."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    agent_profile: str
    work_item_id: int
    work_type: str
    priority: Literal["P0", "P1", "P2", "P3"]
    prompt_context: str
    timeout_seconds: int
    correlation_id: str

    # Optional fields
    tools_allowlist: list[str] = Field(default_factory=list)
    workspace_ref: str | None = None
    session_ref: str | None = None
    budget_limit: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AdapterResult(BaseModel):
    """Normalized output from every adapter run (ADR-0003 §Standard Output)."""

    model_config = ConfigDict(frozen=True)

    status: AdapterStatus
    started_at: datetime
    finished_at: datetime

    # Excerpts — adapters must truncate large outputs before setting these
    stdout_excerpt: str = ""
    stderr_excerpt: str | None = None

    # Result payload for downstream consumers
    result_payload: dict[str, Any] = Field(default_factory=dict)

    # Usage / cost
    usage: UsageReport | None = None
    cost_usd: float = 0.0

    # Session handoff
    session_before: str | None = None
    session_after: str | None = None

    # Runtime-specific
    external_run_id: str | None = None
    exit_code: int | None = None

    # Error detail
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AdapterBase(ABC):
    """Contract that all Nexus runtime adapters must satisfy.

    Nexus Core never talks to adapter implementations directly — only to
    this interface. Adding a new runtime = implementing these 7 methods.
    """

    @abstractmethod
    async def describe(self) -> AdapterDescription:
        """Return adapter identity, execution mode, session model, and capabilities."""

    @abstractmethod
    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        """Check binaries, auth, network, and prerequisites before any invocation."""

    @abstractmethod
    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        """Execute one unit of work for one agent against one work_item."""

    @abstractmethod
    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        """Continue a previously known session when the runtime supports it.

        Adapters that only support ephemeral mode should return
        AdapterResult(status="environment_error", error_code="SESSION_NOT_SUPPORTED", ...).
        """

    @abstractmethod
    async def cancel_run(self, request: AdapterRequest) -> None:
        """Attempt graceful stop, then force termination."""

    @abstractmethod
    async def collect_usage(self, run_handle: object) -> UsageReport:
        """Return normalized usage and cost for audit and budget enforcement.

        Missing usage data is an audit incident — never return zeros silently
        when actual usage occurred.
        """

    @abstractmethod
    async def healthcheck(self, config: dict[str, Any]) -> bool:
        """Lightweight readiness probe for dashboard and operator visibility."""
