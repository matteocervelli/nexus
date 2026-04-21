"""HTTP adapter — dispatches work to a remote HTTP agent endpoint.

Two invocation modes:
- sync: POST request, wait for terminal response.
- async: POST returns run_id, poll status endpoint until done or timeout.

All config arrives via AdapterRequest.extra (stateless adapter).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
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
_HEALTHCHECK_TIMEOUT = 2.0
_VALID_MODES = {"sync", "async"}
# All statuses that AdapterStatus recognises as terminal — must match AdapterBase contract
_TERMINAL_STATUSES = {
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "budget_blocked",
    "environment_error",
}


class HttpAdapter(AdapterBase):
    """Adapter that dispatches work to a remote HTTP agent endpoint."""

    async def describe(self) -> AdapterDescription:
        return AdapterDescription(
            adapter_id="http",
            execution_mode="http",
            session_mode=SessionMode.EPHEMERAL,
            capabilities=["remote-exec"],
        )

    async def validate_environment(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []

        base_url = config.get("base_url")
        if not base_url:
            errors.append("'base_url' is required")
        else:
            parsed = urlparse(str(base_url))
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(f"'base_url' is not a valid HTTP URL: {base_url!r}")
            elif parsed.scheme == "http" and config.get("auth_headers"):
                # auth_headers over cleartext HTTP exposes credentials in transit.
                # Permitted only for localhost/loopback; reject for any other host.
                host = parsed.hostname or ""
                if host not in ("localhost", "127.0.0.1", "::1"):
                    errors.append(
                        "'auth_headers' must not be used with a non-TLS 'base_url' "
                        "(credentials would be transmitted in cleartext). "
                        "Use https:// for remote endpoints."
                    )

        if not config.get("endpoint"):
            errors.append("'endpoint' is required")

        mode = config.get("mode")
        if mode not in _VALID_MODES:
            errors.append(f"'mode' must be one of {sorted(_VALID_MODES)!r}, got {mode!r}")
        elif mode == "async":
            status_endpoint = config.get("status_endpoint", "")
            if "{run_id}" not in str(status_endpoint):
                errors.append(
                    "'status_endpoint' must contain '{run_id}' placeholder for async mode"
                )

        return ValidationResult(ok=len(errors) == 0, errors=errors)

    async def invoke_heartbeat(self, request: AdapterRequest) -> AdapterResult:
        started_at = datetime.now(tz=UTC)
        extra = request.extra
        base_url: str = extra.get("base_url", "")
        endpoint: str = extra.get("endpoint", "")
        # Warn loudly when prompt payload is sent over cleartext HTTP to a non-localhost host.
        # Acceptable for private networks (Tailscale VPN) — not for public internet endpoints.
        _warn_if_insecure(base_url, extra.get("auth_headers"))
        mode: str = extra.get("mode", "sync")
        auth_headers: dict[str, str] = extra.get("auth_headers") or {}

        log = logger.bind(work_item_id=request.work_item_id, mode=mode, base_url=base_url)

        try:
            async with asyncio.timeout(request.timeout_seconds):
                if mode == "sync":
                    return await self._invoke_sync(
                        request, base_url, endpoint, auth_headers, started_at, log
                    )
                else:
                    status_endpoint: str = extra.get("status_endpoint", "")
                    poll_interval: float = float(extra.get("poll_interval_seconds", 5))
                    return await self._invoke_async(
                        request,
                        base_url,
                        endpoint,
                        auth_headers,
                        status_endpoint,
                        poll_interval,
                        started_at,
                        log,
                    )
        except TimeoutError:
            finished_at = datetime.now(tz=UTC)
            log.warning("http.timed_out")
            return AdapterResult(
                status="timed_out",
                started_at=started_at,
                finished_at=finished_at,
                error_code="TIMEOUT",
                error_message=f"invocation exceeded {request.timeout_seconds}s",
                usage=UsageReport(tokens_used=0, cost_usd=0.0),
            )
        except Exception as exc:
            finished_at = datetime.now(tz=UTC)
            log.exception("http.unexpected_error", error=str(exc))
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="UNEXPECTED_ERROR",
                error_message=str(exc),
            )

    async def _invoke_sync(
        self,
        request: AdapterRequest,
        base_url: str,
        endpoint: str,
        auth_headers: dict[str, str],
        started_at: datetime,
        log: Any,
    ) -> AdapterResult:
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.post(
                endpoint,
                json={
                    "prompt_context": request.prompt_context,
                    "correlation_id": request.correlation_id,
                },
                headers=auth_headers,
            )

        finished_at = datetime.now(tz=UTC)
        log.info("http.sync.response", status_code=resp.status_code)

        if resp.status_code >= 400:
            return AdapterResult(
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error_code="HTTP_ERROR",
                error_message=f"remote returned HTTP {resp.status_code}",
                stdout_excerpt=resp.text[:_EXCERPT_MAX],
            )

        return _normalize_terminal_response(resp.json(), started_at, finished_at)

    async def _invoke_async(
        self,
        request: AdapterRequest,
        base_url: str,
        endpoint: str,
        auth_headers: dict[str, str],
        status_endpoint: str,
        poll_interval: float,
        started_at: datetime,
        log: Any,
    ) -> AdapterResult:
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.post(
                endpoint,
                json={
                    "prompt_context": request.prompt_context,
                    "correlation_id": request.correlation_id,
                },
                headers=auth_headers,
            )
            if resp.status_code >= 400:
                finished_at = datetime.now(tz=UTC)
                return AdapterResult(
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    error_code="HTTP_ERROR",
                    error_message=f"remote returned HTTP {resp.status_code} on initial POST",
                    stdout_excerpt=resp.text[:_EXCERPT_MAX],
                )

            run_id: str = resp.json().get("run_id") or ""
            if not run_id:
                finished_at = datetime.now(tz=UTC)
                return AdapterResult(
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    error_code="MISSING_RUN_ID",
                    error_message="remote POST returned 2xx but no run_id in response body",
                )
            log.info("http.async.started", run_id=run_id)

            poll_url = status_endpoint.replace("{run_id}", run_id)

            while True:
                await asyncio.sleep(poll_interval)
                poll_resp = await client.get(poll_url, headers=auth_headers)
                if poll_resp.status_code >= 400:
                    log.warning(
                        "http.async.poll_error", status_code=poll_resp.status_code, run_id=run_id
                    )
                    finished_at = datetime.now(tz=UTC)
                    return AdapterResult(
                        status="failed",
                        started_at=started_at,
                        finished_at=finished_at,
                        error_code="POLL_HTTP_ERROR",
                        error_message=f"poll returned HTTP {poll_resp.status_code} for run_id={run_id!r}",
                        stdout_excerpt=poll_resp.text[:_EXCERPT_MAX],
                    )
                data = poll_resp.json()
                status = data.get("status", "")
                log.debug("http.async.poll", status=status, run_id=run_id)

                if status in _TERMINAL_STATUSES:
                    finished_at = datetime.now(tz=UTC)
                    result = _normalize_terminal_response(data, started_at, finished_at)
                    # run_id may also come from the poll response
                    if not result.external_run_id:
                        result = result.model_copy(update={"external_run_id": run_id})
                    return result

    async def resume_session(self, request: AdapterRequest) -> AdapterResult:
        raise NotImplementedError("HttpAdapter is ephemeral — resume_session is not supported")

    async def cancel_run(self, request: AdapterRequest) -> None:
        # Phase 2: implement remote cancellation via DELETE or POST /runs/{run_id}/cancel.
        # For now, local timeout stops polling; the remote job continues until it self-terminates.
        logger.info("http.cancel_run.noop", work_item_id=request.work_item_id)

    async def collect_usage(self, run_handle: object) -> UsageReport:
        # Usage is captured inline during invoke_heartbeat from the remote response.
        return UsageReport(tokens_used=0, cost_usd=0.0)

    async def healthcheck(self, config: dict[str, Any]) -> bool:
        base_url = config.get("base_url")
        if not base_url:
            return False
        health_path: str = config.get("health_path", "/health")
        try:
            async with httpx.AsyncClient(
                base_url=str(base_url), timeout=_HEALTHCHECK_TIMEOUT
            ) as client:
                resp = await client.get(health_path)
                return resp.status_code == 200
        except Exception:
            return False


def _warn_if_insecure(base_url: str, auth_headers: Any) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        return
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return
    logger.warning(
        "http.insecure_transport",
        base_url=base_url,
        has_auth=bool(auth_headers),
        note="prompt_context transmitted in cleartext to non-localhost host; use https:// for public/remote endpoints",
    )


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _normalize_terminal_response(
    data: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
) -> AdapterResult:
    raw_status = data.get("status", "failed")
    status: AdapterStatus = (
        raw_status
        if raw_status
        in ("succeeded", "failed", "cancelled", "timed_out", "budget_blocked", "environment_error")
        else "failed"
    )

    tokens_used = _safe_int(data.get("tokens_used"), default=0)
    cost_usd = _safe_float(data.get("cost_usd"), default=0.0)
    if tokens_used == 0 and cost_usd == 0.0 and raw_status == "succeeded":
        logger.warning("http.usage.missing", note="remote did not return token counts")

    output = str(data.get("output", ""))
    run_id = data.get("run_id")

    return AdapterResult(
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        stdout_excerpt=output[:_EXCERPT_MAX],
        usage=UsageReport(tokens_used=tokens_used, cost_usd=cost_usd),
        cost_usd=cost_usd,
        external_run_id=run_id,
    )
