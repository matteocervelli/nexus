"""Claude Code CLI adapter for Nexus.

Executes agent work items via `claude --output-format json -p` subprocess.
Supports session resumption via --session-id.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import time
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

_EXCERPT_LIMIT = 4096


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _truncate(text: str) -> str:
    return text[:_EXCERPT_LIMIT]


class ClaudeAdapter(AdapterBase):
    """Subprocess adapter for the Claude Code CLI."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="claude-code-cli",
            execution_mode="subprocess",
            session_mode=SessionMode.RESUMABLE,
            capabilities=["code", "search", "edit"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        if shutil.which("claude") is None:
            errors.append("`claude` binary not found in PATH")
        return ValidationResult(ok=len(errors) == 0, errors=errors)

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request)

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request)

    async def cancel_run(self, request: AdapterRequest) -> None:
        # cancel_run operates on a live proc; tracked externally by scheduler
        logger.info("cancel_run.noop", agent_id=request.agent_id)

    async def collect_usage(self, run_handle: object) -> UsageReport:
        if isinstance(run_handle, AdapterResult):
            payload = run_handle.result_payload
        elif isinstance(run_handle, dict):
            payload = run_handle
        else:
            payload = {}

        tokens_in = int(payload.get("_tokens_input", 0))
        tokens_out = int(payload.get("_tokens_output", 0))
        cost = float(payload.get("_cost_usd", 0.0))
        return UsageReport(
            tokens_used=tokens_in + tokens_out,
            cost_usd=cost,
            details={"input_tokens": tokens_in, "output_tokens": tokens_out},
        )

    async def healthcheck(self, config: dict[str, Any]) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_argv(self, request: AdapterRequest) -> list[str]:
        argv = [
            "claude",
            "--system-prompt", request.agent_profile,
            "--output-format", "json",
            "-p", request.prompt_context,
            "--no-color",
        ]
        if request.session_ref is not None:
            argv += ["--session-id", request.session_ref]
        return argv

    async def _run(self, request: AdapterRequest) -> AdapterResult:
        argv = self._build_argv(request)
        started_at = _now()
        t0 = time.monotonic()

        log = logger.bind(
            agent_id=request.agent_id,
            work_item_id=request.work_item_id,
            correlation_id=request.correlation_id,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except Exception as exc:
            log.error("spawn.failed", error=str(exc))
            finished_at = _now()
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="SPAWN_ERROR",
                error_message=str(exc),
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=request.timeout_seconds,
            )
        except asyncio.TimeoutError:
            finished_at = _now()
            log.warning("run.timed_out", timeout_seconds=request.timeout_seconds)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except OSError:
                    proc.kill()
            return AdapterResult(
                status="timed_out",
                started_at=started_at,
                finished_at=finished_at,
            )

        finished_at = _now()
        duration_ms = int((time.monotonic() - t0) * 1000)

        stdout_text = stdout_bytes.decode(errors="replace")
        stderr_text = stderr_bytes.decode(errors="replace")

        if proc.returncode != 0:
            log.error("run.failed", exit_code=proc.returncode, stderr=stderr_text[:200])
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                exit_code=proc.returncode,
                stdout_excerpt=_truncate(stdout_text),
                stderr_excerpt=_truncate(stderr_text),
                error_code="NONZERO_EXIT",
                error_message=stderr_text or f"exit code {proc.returncode}",
            )

        try:
            envelope = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            log.error("parse.failed", error=str(exc))
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                exit_code=proc.returncode,
                stdout_excerpt=_truncate(stdout_text),
                error_code="PARSE_ERROR",
                error_message=f"JSON parse error: {exc}",
            )

        usage_raw = envelope.get("usage", {})
        tokens_in = int(usage_raw.get("input_tokens", 0))
        tokens_out = int(usage_raw.get("output_tokens", 0))
        cost = float(envelope.get("cost_usd", 0.0))
        session_after = envelope.get("session_id")

        usage = UsageReport(
            tokens_used=tokens_in + tokens_out,
            cost_usd=cost,
            details={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "cache_read_input_tokens": usage_raw.get("cache_read_input_tokens", 0),
                "cache_creation_input_tokens": usage_raw.get("cache_creation_input_tokens", 0),
                "duration_ms": duration_ms,
            },
        )

        result_payload: dict[str, Any] = {
            "output": envelope.get("result", ""),
            "_tokens_input": tokens_in,
            "_tokens_output": tokens_out,
            "_cost_usd": cost,
        }

        log.info("run.succeeded", tokens_used=usage.tokens_used, duration_ms=duration_ms)
        return AdapterResult(
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
            exit_code=0,
            stdout_excerpt=_truncate(stdout_text),
            stderr_excerpt=_truncate(stderr_text) if stderr_text else None,
            result_payload=result_payload,
            usage=usage,
            cost_usd=cost,
            session_before=request.session_ref,
            session_after=session_after,
        )
