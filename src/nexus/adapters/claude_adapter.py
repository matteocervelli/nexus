"""Claude Code CLI adapter for Nexus — uses claude-agent-sdk.

Executes agent work items via the claude_agent_sdk.query async generator.
Supports session resumption via ClaudeAgentOptions.resume.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

from nexus.adapter_base import (
    AdapterBase,
    AdapterDescription,
    AdapterRequest,
    AdapterResult,
    SessionMode,
    UsageReport,
    ValidationResult,
)
from nexus.adapters._claude_sdk import _is_transient, _read_system_prompt, _stderr_handler

logger = structlog.get_logger(__name__)

_EXCERPT_LIMIT = 4096
_MINIMAL_TOOLS = ["Read", "Glob", "Grep"]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _truncate(text: str) -> str:
    return text[:_EXCERPT_LIMIT]


class ClaudeAdapter(AdapterBase):
    """SDK-based adapter for the Claude Code CLI."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="claude-code-cli",
            execution_mode="subprocess",
            session_mode=SessionMode.RESUMABLE,
            capabilities=["code", "search", "edit"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        try:
            import claude_agent_sdk as _sdk  # noqa: F401

            _ = _sdk.query  # ensure the symbol actually exists in this version
            return ValidationResult(ok=True)
        except (ImportError, AttributeError) as exc:
            return ValidationResult(ok=False, errors=[f"`claude_agent_sdk` unusable: {exc}"])

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request)

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request)

    async def cancel_run(self, request: AdapterRequest) -> None:
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
            import claude_agent_sdk as _sdk  # noqa: F401

            _ = _sdk.query
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self, request: AdapterRequest) -> AdapterResult:
        started_at = _now()
        t0 = time.monotonic()
        extra = request.extra or {}

        log = logger.bind(
            agent_id=request.agent_id,
            work_item_id=request.work_item_id,
            correlation_id=request.correlation_id,
        )

        system_prompt = _read_system_prompt(request.agent_profile)
        allowed_tools = list(request.tools_allowlist) if request.tools_allowlist else _MINIMAL_TOOLS

        opts = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=extra.get("model") or None,
            allowed_tools=allowed_tools,
            max_turns=int(extra.get("max_turns", 300)),
            permission_mode="bypassPermissions",
            resume=request.session_ref or None,
            cwd=extra.get("cwd"),
            stderr=_stderr_handler,
            # Pass stream-close timeout per-invocation via env, not os.environ (avoids race)
            env={"CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": str(int(request.timeout_seconds * 1000))},
        )

        text_parts: list[str] = []
        session_after: str | None = None
        usage_raw: dict[str, Any] = {}
        cost: float = 0.0

        async def _stream() -> None:
            nonlocal session_after, usage_raw, cost
            async for msg in query(prompt=request.prompt_context, options=opts):
                if msg is None:
                    continue
                if isinstance(msg, ResultMessage):
                    session_after = msg.session_id
                    usage_raw = msg.usage or {}
                    cost = float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
                    continue
                if isinstance(msg, AssistantMessage):
                    for block in getattr(msg, "content", []):
                        text = getattr(block, "text", None)
                        if text:
                            text_parts.append(text)

        for attempt in range(2):
            try:
                await asyncio.wait_for(_stream(), timeout=request.timeout_seconds)
                break  # success
            except TimeoutError:
                finished_at = _now()
                log.warning("run.timed_out", timeout_seconds=request.timeout_seconds)
                return AdapterResult(
                    status="timed_out",
                    started_at=started_at,
                    finished_at=finished_at,
                )
            except Exception as exc:
                delay = _is_transient(exc)
                if delay is not None and attempt == 0:
                    log.warning("run.transient_retry", error=str(exc), delay=delay)
                    await asyncio.sleep(delay)
                    text_parts.clear()
                    continue
                # Non-transient or second attempt failed
                finished_at = _now()
                error_code = "TRANSIENT_EXHAUSTED" if delay is not None else "SDK_ERROR"
                log.error("run.failed", error_code=error_code, error=str(exc))
                return AdapterResult(
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    error_code=error_code,
                    error_message=str(exc),
                )

        finished_at = _now()
        duration_ms = int((time.monotonic() - t0) * 1000)

        tokens_in = int(usage_raw.get("input_tokens", 0))
        tokens_out = int(usage_raw.get("output_tokens", 0))

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

        output_text = "\n".join(text_parts)
        result_payload: dict[str, Any] = {
            "output": output_text,
            "_tokens_input": tokens_in,
            "_tokens_output": tokens_out,
            "_cost_usd": cost,
        }

        log.info("run.succeeded", tokens_used=usage.tokens_used, duration_ms=duration_ms)
        return AdapterResult(
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
            result_payload=result_payload,
            usage=usage,
            cost_usd=cost,
            session_before=request.session_ref,
            session_after=session_after,
        )
