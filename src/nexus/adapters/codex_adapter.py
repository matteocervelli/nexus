"""Codex CLI adapter for the Nexus orchestration engine.

Spawns `codex -p <prompt>` as an ephemeral subprocess. No session model.
Timeout detection is elapsed-time-based because Codex exits 0 on SIGTERM.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from nexus.adapter_base import (
    AdapterBase,
    AdapterDescription,
    AdapterRequest,
    AdapterResult,
    AdapterStatus,
    SessionMode,
    UsageReport,
    ValidationResult,
)

logger = structlog.get_logger(__name__)

_EXCERPT_MAX = 4096


class CodexAdapter(AdapterBase):
    """Codex CLI execution backend — ephemeral subprocess, no sessions."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="codex-cli",
            execution_mode="subprocess",
            session_mode=SessionMode.EPHEMERAL,
            capabilities=["code", "search"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        if shutil.which("codex") is None:
            return ValidationResult(ok=False, errors=["codex binary not found in PATH"])
        return ValidationResult(ok=True)

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        started_at = datetime.now(UTC)
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                "codex",
                "-p",
                request.prompt_context,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            finished_at = datetime.now(UTC)
            logger.error("codex.spawn_error", work_item_id=request.work_item_id, error=str(exc))
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="SPAWN_ERROR",
                error_message=str(exc),
            )

        try:
            stdout_bytes, stderr_bytes = await proc.communicate()
        finally:
            elapsed = time.monotonic() - start

        stdout_decoded = stdout_bytes.decode(errors="replace")
        stderr_decoded = stderr_bytes.decode(errors="replace") if stderr_bytes else None
        tokens_used = len(stdout_decoded) // 4

        # Elapsed-based timeout detection: Codex exits 0 on SIGTERM so exit code is unreliable.
        status: AdapterStatus
        if elapsed >= request.timeout_seconds:
            status = "timed_out"
        elif proc.returncode == 0:
            status = "succeeded"
        else:
            status = "failed"

        finished_at = datetime.now(UTC)
        logger.info(
            "codex.run_complete",
            work_item_id=request.work_item_id,
            status=status,
            elapsed=round(elapsed, 2),
            tokens_used=tokens_used,
        )

        return AdapterResult(
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            stdout_excerpt=stdout_decoded[:_EXCERPT_MAX],
            stderr_excerpt=stderr_decoded[:_EXCERPT_MAX] if stderr_decoded else None,
            exit_code=proc.returncode,
            usage=UsageReport(tokens_used=tokens_used, cost_usd=0.0),
            cost_usd=0.0,
        )

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        raise NotImplementedError("Codex does not support sessions")

    async def cancel_run(self, request: AdapterRequest) -> None:
        # cancel_run is best-effort; active proc reference not tracked here
        # (Nexus Core is responsible for process lifecycle management)
        logger.warning("codex.cancel_run_noop", work_item_id=request.work_item_id)

    async def collect_usage(self, run_handle: object) -> UsageReport:
        tokens = 0
        if isinstance(run_handle, dict):
            tokens = run_handle.get("tokens_used", 0)
        return UsageReport(tokens_used=tokens, cost_usd=0.0)

    async def healthcheck(self, config: dict[str, Any]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "codex",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0
        except Exception:
            return False
