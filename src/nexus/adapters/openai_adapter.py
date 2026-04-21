"""Codex SDK adapter for Nexus — JSON-RPC over local codex binary.

Uses openai_codex_sdk (PyPI) to control the codex CLI process.
Supports session resumption via Thread.resume_thread.
State is returned via AdapterResult; nothing is written to disk.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from openai_codex_sdk import (
    AgentMessageItem,
    Codex,
    ItemCompletedEvent,
    ThreadErrorEvent,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
)
from openai_codex_sdk.errors import CodexExecError

from nexus.adapter_base import (
    AdapterBase,
    AdapterDescription,
    AdapterRequest,
    AdapterResult,
    SessionMode,
    UsageReport,
    ValidationResult,
)
from nexus.adapters._openai_pricing import estimate_cost
from nexus.adapters._profile import read_system_prompt

logger = structlog.get_logger(__name__)

_EXCERPT_LIMIT = 4096


def _now() -> datetime:
    return datetime.now(tz=UTC)


class CodexAdapter(AdapterBase):
    """Codex SDK adapter — subprocess JSON-RPC, supports session resumption."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="codex-sdk",
            execution_mode="subprocess",
            session_mode=SessionMode.RESUMABLE,
            capabilities=["code", "search", "edit"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        try:
            import openai_codex_sdk as _  # noqa: F401 — verify importability

            try:
                Codex()  # patchable via module-level name
            except CodexExecError as exc:
                errors.append(f"codex binary not found: {exc}")
        except ImportError as exc:
            errors.append(f"openai_codex_sdk not importable: {exc}")
        return ValidationResult(ok=not errors, errors=errors)

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request, resume=False)

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        return await self._run(request, resume=True)

    async def cancel_run(self, request: AdapterRequest) -> None:
        logger.info("codex.cancel_run.noop", agent_id=request.agent_id)

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
            Codex()  # patchable via module-level name
            return True
        except CodexExecError:
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self, request: AdapterRequest, *, resume: bool) -> AdapterResult:
        started_at = _now()
        t0 = time.monotonic()
        extra = request.extra or {}
        model: str | None = extra.get("model") or None
        cwd: str | None = extra.get("cwd") or None
        sandbox_mode: str = extra.get("sandbox_mode", "workspace-write")
        approval_policy: str = extra.get("approval_policy", "on-request")

        log = logger.bind(
            agent_id=request.agent_id,
            work_item_id=request.work_item_id,
            correlation_id=request.correlation_id,
        )

        if request.tools_allowlist:
            log.warning(
                "codex.tools_allowlist.ignored",
                reason="Codex SDK does not support tools_allowlist; use extra.sandbox_mode instead",
            )

        system_prompt = read_system_prompt(request.agent_profile)
        full_prompt = (
            f"{system_prompt}\n\n{request.prompt_context}"
            if system_prompt
            else request.prompt_context
        )

        thread_opts: dict[str, Any] = {
            "model": model,
            "working_directory": cwd,
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
        }

        codex = Codex()
        if resume and request.session_ref:
            thread = codex.resume_thread(request.session_ref, thread_opts)
        else:
            thread = codex.start_thread(thread_opts)

        text_parts: list[str] = []
        session_after: str | None = None
        usage_raw: Any = None

        async def _stream() -> None:
            nonlocal session_after, usage_raw
            streamed = await thread.run_streamed(full_prompt)
            async for event in streamed.events:
                if isinstance(event, ThreadStartedEvent):
                    session_after = event.thread_id
                elif isinstance(event, ItemCompletedEvent):
                    item = event.item
                    if isinstance(item, AgentMessageItem):
                        text_parts.append(item.text)
                elif isinstance(event, TurnCompletedEvent):
                    usage_raw = event.usage
                elif isinstance(event, TurnFailedEvent):
                    raise RuntimeError(event.error.message)
                elif isinstance(event, ThreadErrorEvent):
                    raise RuntimeError(event.message)

        try:
            await asyncio.wait_for(_stream(), timeout=float(request.timeout_seconds))
        except TimeoutError:
            finished_at = _now()
            log.warning("codex.timed_out", timeout_seconds=request.timeout_seconds)
            return AdapterResult(
                status="timed_out",
                started_at=started_at,
                finished_at=finished_at,
                error_code="TIMEOUT",
                error_message=f"Timed out after {request.timeout_seconds}s",
            )
        except Exception as exc:
            finished_at = _now()
            log.error("codex.run_failed", error=str(exc))
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="CODEX_SDK_ERROR",
                error_message=str(exc),
            )

        finished_at = _now()
        duration_ms = int((time.monotonic() - t0) * 1000)

        tokens_in = usage_raw.input_tokens if usage_raw else 0
        tokens_out = usage_raw.output_tokens if usage_raw else 0
        cost = estimate_cost(model or "gpt-4o", tokens_in, tokens_out)
        session_id = session_after or thread.id
        text = "\n".join(text_parts)

        usage = UsageReport(
            tokens_used=tokens_in + tokens_out,
            cost_usd=cost,
            details={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "model": model,
                "duration_ms": duration_ms,
                "cost_source": "estimated",
            },
        )

        result_payload: dict[str, Any] = {
            "output": text,
            "_tokens_input": tokens_in,
            "_tokens_output": tokens_out,
            "_cost_usd": cost,
        }

        log.info("codex.run_complete", tokens_used=usage.tokens_used, duration_ms=duration_ms)
        return AdapterResult(
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
            stdout_excerpt=text[:_EXCERPT_LIMIT],
            result_payload=result_payload,
            usage=usage,
            cost_usd=cost,
            session_before=request.session_ref,
            session_after=session_id,
        )
