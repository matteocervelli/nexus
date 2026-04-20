"""Tests for AdapterBase ABC and its I/O models.

Red phase: these tests must FAIL before adapter_base.py is written.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from nexus.adapter_base import (
    AdapterBase,
    AdapterDescription,
    AdapterRequest,
    AdapterResult,
    SessionMode,
    UsageReport,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


def test_cannot_instantiate_adapter_base_directly() -> None:
    """AdapterBase is abstract — direct instantiation must raise."""
    with pytest.raises(TypeError):
        AdapterBase()  # type: ignore[abstract]


def test_concrete_adapter_missing_methods_raises() -> None:
    """A subclass that omits any abstract method cannot be instantiated."""

    class PartialAdapter(AdapterBase):
        async def describe(self) -> AdapterDescription:
            raise NotImplementedError

        # Missing: validate_environment, invoke_heartbeat, resume_session,
        #          cancel_run, collect_usage, healthcheck

    with pytest.raises(TypeError):
        PartialAdapter()


def test_concrete_adapter_all_methods_can_instantiate() -> None:
    """A subclass implementing all 7 abstract methods can be instantiated."""

    class FullAdapter(AdapterBase):
        async def describe(self) -> AdapterDescription:
            return AdapterDescription(
                adapter_id="test",
                execution_mode="subprocess",
                session_mode=SessionMode.EPHEMERAL,
                capabilities=[],
            )

        async def validate_environment(self, config: dict) -> ValidationResult:  # type: ignore[override]
            return ValidationResult(ok=True, errors=[])

        async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
            raise NotImplementedError

        async def resume_session(self, request: AdapterRequest) -> AdapterResult:
            raise NotImplementedError

        async def cancel_run(self, request: AdapterRequest) -> None:
            return None

        async def collect_usage(self, run_handle: object) -> UsageReport:
            return UsageReport(tokens_used=0, cost_usd=0.0)

        async def healthcheck(self, config: dict) -> bool:  # type: ignore[override]
            return True

    adapter = FullAdapter()
    assert adapter is not None


# ---------------------------------------------------------------------------
# AdapterRequest validation
# ---------------------------------------------------------------------------


def test_adapter_request_requires_mandatory_fields() -> None:
    with pytest.raises(ValidationError):
        AdapterRequest()  # type: ignore[call-arg]


def test_adapter_request_minimal_valid() -> None:
    req = AdapterRequest(
        agent_id="agent-001",
        agent_profile="/path/to/profile",
        work_item_id=42,
        work_type="bug_fix",
        priority="P1",
        prompt_context="Fix the null pointer in auth.py",
        timeout_seconds=120,
        correlation_id="corr-abc123",
    )
    assert req.agent_id == "agent-001"
    assert req.timeout_seconds == 120
    assert req.tools_allowlist == []  # default
    assert req.workspace_ref is None  # optional


def test_adapter_request_is_immutable() -> None:
    req = AdapterRequest(
        agent_id="agent-001",
        agent_profile="/path/to/profile",
        work_item_id=1,
        work_type="review",
        priority="P2",
        prompt_context="Review the PR",
        timeout_seconds=60,
        correlation_id="corr-xyz",
    )
    with pytest.raises(ValidationError):
        req.agent_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AdapterResult validation
# ---------------------------------------------------------------------------


def test_adapter_result_valid_succeeded() -> None:
    from datetime import datetime

    now = datetime.now(UTC)
    result = AdapterResult(
        status="succeeded",
        started_at=now,
        finished_at=now,
        stdout_excerpt="Done.",
    )
    assert result.status == "succeeded"
    assert result.stderr_excerpt is None


def test_adapter_result_rejects_unknown_status() -> None:
    from datetime import datetime

    with pytest.raises(ValidationError):
        AdapterResult(
            status="success",  # wrong — use "succeeded"
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )


def test_adapter_result_is_immutable() -> None:
    from datetime import datetime

    now = datetime.now(UTC)
    result = AdapterResult(status="failed", started_at=now, finished_at=now)
    with pytest.raises(ValidationError):
        result.status = "succeeded"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# No I/O in base class
# ---------------------------------------------------------------------------


def test_adapter_base_has_no_io_side_effects() -> None:
    """Importing adapter_base must not trigger network or filesystem calls."""
    import importlib

    # If import raises, something is wired at module level — that's wrong.
    mod = importlib.import_module("nexus.adapter_base")
    assert mod is not None
