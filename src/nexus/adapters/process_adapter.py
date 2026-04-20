"""Generic local-executable adapter.

Spawns any local binary as an ephemeral subprocess. No LLM cost tracking.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
from datetime import datetime, timezone
from typing import Any

import structlog

from nexus.adapter_base import (
    AdapterBase,
    AdapterDescription,
    AdapterRequest,
    AdapterResult,
    SessionMode,
    UsageReport,
    ValidationResult,
)

logger = structlog.get_logger(__name__)

_EXCERPT_MAX = 4096
_SIGKILL_WAIT = 5


class ProcessAdapter(AdapterBase):
    """Adapter for any local executable invoked as a subprocess."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="process",
            execution_mode="subprocess",
            session_mode=SessionMode.EPHEMERAL,
            capabilities=["local-exec"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        executable = config.get("executable")
        if not executable:
            return ValidationResult(ok=False, errors=["'executable' missing from config"])

        resolved = shutil.which(executable)
        if resolved is None:
            return ValidationResult(ok=False, errors=[f"executable not found on PATH: {executable}"])

        if not os.access(resolved, os.X_OK):
            return ValidationResult(ok=False, errors=[f"file exists but is not executable: {resolved}"])

        return ValidationResult(ok=True)

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        started_at = datetime.now(tz=timezone.utc)
        executable = request.extra.get("executable")
        args: list[str] = request.extra.get("args", [])
        stdin_mode: str = request.extra.get("stdin_mode", "prompt")

        resolved = shutil.which(executable) if executable else None
        if resolved is None:
            finished_at = datetime.now(tz=timezone.utc)
            return AdapterResult(
                status="environment_error",
                started_at=started_at,
                finished_at=finished_at,
                error_code="EXECUTABLE_NOT_FOUND",
                error_message=f"shutil.which({executable!r}) returned None",
            )

        cmd = [resolved] + list(args)
        stdin_data = request.prompt_context.encode() if stdin_mode == "prompt" else None

        log = logger.bind(work_item_id=request.work_item_id, cmd=cmd[0])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            log.info("process.started", pid=proc.pid)

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=stdin_data),
                    timeout=request.timeout_seconds,
                )
            except asyncio.TimeoutError:
                log.warning("process.timed_out", pid=proc.pid)
                await _terminate(proc)
                finished_at = datetime.now(tz=timezone.utc)
                return AdapterResult(
                    status="timed_out",
                    started_at=started_at,
                    finished_at=finished_at,
                    error_code="TIMEOUT",
                    error_message=f"process exceeded {request.timeout_seconds}s",
                    usage=UsageReport(tokens_used=0, cost_usd=0.0),
                )

        except Exception as exc:
            log.exception("process.spawn_error", error=str(exc))
            finished_at = datetime.now(tz=timezone.utc)
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="SPAWN_ERROR",
                error_message=str(exc),
            )

        finished_at = datetime.now(tz=timezone.utc)
        exit_code = proc.returncode
        status = "succeeded" if exit_code == 0 else "failed"
        log.info("process.finished", exit_code=exit_code, status=status)

        return AdapterResult(
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            stdout_excerpt=stdout_bytes.decode(errors="replace")[:_EXCERPT_MAX],
            stderr_excerpt=stderr_bytes.decode(errors="replace")[:_EXCERPT_MAX] or None,
            exit_code=exit_code,
            usage=UsageReport(tokens_used=0, cost_usd=0.0),
        )

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        raise NotImplementedError("ProcessAdapter is ephemeral — resume_session is not supported")

    async def cancel_run(self, request: AdapterRequest) -> None:
        logger.info("process.cancel_run.noop", work_item_id=request.work_item_id)

    async def collect_usage(self, run_handle: object) -> UsageReport:
        return UsageReport(tokens_used=0, cost_usd=0.0)

    async def healthcheck(self, config: dict[str, Any]) -> bool:
        return True


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM then SIGKILL after _SIGKILL_WAIT seconds."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGKILL_WAIT)
    except asyncio.TimeoutError:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
