"""Tests for HttpAdapter — TDD red phase written before implementation."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from nexus.adapter_base import AdapterRequest, SessionMode
from nexus.adapters.http_adapter import HttpAdapter


def make_request(**overrides) -> AdapterRequest:
    defaults = {
        "agent_id": "test-agent",
        "agent_profile": "test-profile",
        "work_item_id": 1,
        "work_type": "test",
        "priority": "P2",
        "prompt_context": "do the thing",
        "timeout_seconds": 5,
        "correlation_id": "corr-123",
        "extra": {
            "base_url": "http://runner.example.com",
            "endpoint": "/v1/invoke",
            "mode": "sync",
        },
    }
    defaults.update(overrides)
    return AdapterRequest(**defaults)


class TestHttpAdapterDescribe:
    async def test_describe_returns_expected(self):
        adapter = HttpAdapter()
        desc = await adapter.describe()
        assert desc.adapter_id == "http"
        assert desc.execution_mode == "http"
        assert desc.session_mode == SessionMode.EPHEMERAL
        assert "remote-exec" in desc.capabilities


class TestHttpAdapterValidateEnvironment:
    async def test_missing_base_url_returns_not_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment({"endpoint": "/v1/invoke", "mode": "sync"})
        assert result.ok is False
        assert any("base_url" in e for e in result.errors)

    async def test_missing_endpoint_returns_not_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment({"base_url": "http://x.com", "mode": "sync"})
        assert result.ok is False
        assert any("endpoint" in e for e in result.errors)

    async def test_invalid_mode_returns_not_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {"base_url": "http://x.com", "endpoint": "/v1/invoke", "mode": "grpc"}
        )
        assert result.ok is False
        assert any("mode" in e for e in result.errors)

    async def test_async_mode_without_run_id_placeholder_returns_not_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {
                "base_url": "http://x.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/latest",  # missing {run_id}
            }
        )
        assert result.ok is False
        assert any("run_id" in e for e in result.errors)

    async def test_valid_sync_config_returns_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {"base_url": "http://x.com", "endpoint": "/v1/invoke", "mode": "sync"}
        )
        assert result.ok is True
        assert result.errors == []

    async def test_valid_async_config_returns_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {
                "base_url": "http://x.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
            }
        )
        assert result.ok is True
        assert result.errors == []

    async def test_http_with_auth_headers_on_remote_host_returns_not_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {
                "base_url": "http://remote.example.com",
                "endpoint": "/v1/invoke",
                "mode": "sync",
                "auth_headers": {"Authorization": "Bearer secret"},
            }
        )
        assert result.ok is False
        assert any("cleartext" in e for e in result.errors)

    async def test_http_with_auth_headers_on_localhost_is_ok(self):
        adapter = HttpAdapter()
        result = await adapter.validate_environment(
            {
                "base_url": "http://localhost:9999",
                "endpoint": "/v1/invoke",
                "mode": "sync",
                "auth_headers": {"Authorization": "Bearer local-token"},
            }
        )
        assert result.ok is True


class TestHttpAdapterInvokeHeartbeatSync:
    @respx.mock
    async def test_sync_happy_path_succeeded(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={
                    "status": "succeeded",
                    "output": "hello remote",
                    "tokens_used": 42,
                    "cost_usd": 0.001,
                },
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "succeeded"
        assert "hello remote" in result.stdout_excerpt
        assert result.cost_usd == pytest.approx(0.001)
        assert result.usage is not None
        assert result.usage.tokens_used == 42

    @respx.mock
    async def test_sync_remote_returns_failed(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={"status": "failed", "output": "boom", "tokens_used": 10, "cost_usd": 0.0},
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "failed"

    @respx.mock
    async def test_sync_non_2xx_returns_failed_with_error_code(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(500, json={"detail": "internal error"})
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "failed"
        assert result.error_code == "HTTP_ERROR"

    @respx.mock
    async def test_sync_auth_headers_forwarded(self):
        route = respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={"status": "succeeded", "output": "ok", "tokens_used": 1, "cost_usd": 0.0},
            )
        )
        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "sync",
                "auth_headers": {"Authorization": "Bearer secret-token"},
            }
        )
        await adapter.invoke_heartbeat(req)
        sent = route.calls.last.request
        assert sent.headers.get("authorization") == "Bearer secret-token"

    @respx.mock
    async def test_sync_external_run_id_from_response(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={
                    "status": "succeeded",
                    "output": "done",
                    "tokens_used": 5,
                    "cost_usd": 0.0,
                    "run_id": "remote-run-abc",
                },
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.external_run_id == "remote-run-abc"


class TestHttpAdapterInvokeHeartbeatAsync:
    @respx.mock
    async def test_async_happy_path_with_polling(self):
        # POST returns run_id
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-xyz"})
        )
        # First poll: running; second poll: succeeded
        poll_route = respx.get("http://runner.example.com/v1/runs/run-xyz")
        poll_route.side_effect = [
            Response(200, json={"status": "running"}),
            Response(
                200,
                json={
                    "status": "succeeded",
                    "output": "all done",
                    "tokens_used": 77,
                    "cost_usd": 0.005,
                },
            ),
        ]

        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "succeeded"
        assert "all done" in result.stdout_excerpt
        assert result.usage is not None
        assert result.usage.tokens_used == 77

    @respx.mock
    async def test_async_poll_returns_failed(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-fail"})
        )
        respx.get("http://runner.example.com/v1/runs/run-fail").mock(
            return_value=Response(
                200,
                json={"status": "failed", "output": "error msg", "tokens_used": 5, "cost_usd": 0.0},
            )
        )

        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "failed"

    @respx.mock
    async def test_async_timeout_while_polling(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-slow"})
        )
        # Always returns running — will hit timeout
        respx.get("http://runner.example.com/v1/runs/run-slow").mock(
            return_value=Response(200, json={"status": "running"})
        )

        adapter = HttpAdapter()
        req = make_request(
            timeout_seconds=1,
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            },
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "timed_out"

    @respx.mock
    async def test_async_missing_run_id_returns_failed(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"message": "job accepted"})  # no run_id
        )
        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "failed"
        assert result.error_code == "MISSING_RUN_ID"

    @respx.mock
    async def test_async_poll_4xx_returns_failed(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-gone"})
        )
        respx.get("http://runner.example.com/v1/runs/run-gone").mock(
            return_value=Response(404, text="not found")
        )
        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "failed"
        assert result.error_code == "POLL_HTTP_ERROR"

    @respx.mock
    async def test_async_budget_blocked_is_terminal(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-budget"})
        )
        respx.get("http://runner.example.com/v1/runs/run-budget").mock(
            return_value=Response(
                200,
                json={"status": "budget_blocked", "output": "", "tokens_used": 0, "cost_usd": 0.0},
            )
        )
        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "budget_blocked"

    @respx.mock
    async def test_async_environment_error_is_terminal(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(200, json={"run_id": "run-env"})
        )
        respx.get("http://runner.example.com/v1/runs/run-env").mock(
            return_value=Response(
                200,
                json={
                    "status": "environment_error",
                    "output": "",
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                },
            )
        )
        adapter = HttpAdapter()
        req = make_request(
            extra={
                "base_url": "http://runner.example.com",
                "endpoint": "/v1/invoke",
                "mode": "async",
                "status_endpoint": "/v1/runs/{run_id}",
                "poll_interval_seconds": 0.01,
            }
        )
        result = await adapter.invoke_heartbeat(req)
        assert result.status == "environment_error"


class TestHttpAdapterNormalizeRobustness:
    @respx.mock
    async def test_sync_null_tokens_uses_zero(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={"status": "succeeded", "output": "ok", "tokens_used": None, "cost_usd": None},
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "succeeded"
        assert result.usage is not None
        assert result.usage.tokens_used == 0
        assert result.cost_usd == 0.0

    @respx.mock
    async def test_sync_string_tokens_uses_zero(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={"status": "succeeded", "output": "ok", "tokens_used": "N/A", "cost_usd": ""},
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "succeeded"
        assert result.usage is not None
        assert result.usage.tokens_used == 0

    @respx.mock
    async def test_sync_unknown_status_normalizes_to_failed(self):
        respx.post("http://runner.example.com/v1/invoke").mock(
            return_value=Response(
                200,
                json={"status": "unknown_state", "output": "?", "tokens_used": 1, "cost_usd": 0.0},
            )
        )
        adapter = HttpAdapter()
        result = await adapter.invoke_heartbeat(make_request())
        assert result.status == "failed"


class TestHttpAdapterResumeSession:
    async def test_resume_session_raises(self):
        adapter = HttpAdapter()
        request = make_request()
        with pytest.raises(NotImplementedError):
            await adapter.resume_session(request)


class TestHttpAdapterHealthcheck:
    @respx.mock
    async def test_healthcheck_200_returns_true(self):
        respx.get("http://runner.example.com/health").mock(
            return_value=Response(200, json={"ok": True})
        )
        adapter = HttpAdapter()
        result = await adapter.healthcheck({"base_url": "http://runner.example.com"})
        assert result is True

    @respx.mock
    async def test_healthcheck_500_returns_false(self):
        respx.get("http://runner.example.com/health").mock(return_value=Response(500))
        adapter = HttpAdapter()
        result = await adapter.healthcheck({"base_url": "http://runner.example.com"})
        assert result is False

    @respx.mock
    async def test_healthcheck_missing_base_url_returns_false(self):
        adapter = HttpAdapter()
        result = await adapter.healthcheck({})
        assert result is False

    @respx.mock
    async def test_healthcheck_custom_path(self):
        respx.get("http://runner.example.com/api/ping").mock(
            return_value=Response(200, json={"pong": True})
        )
        adapter = HttpAdapter()
        result = await adapter.healthcheck(
            {"base_url": "http://runner.example.com", "health_path": "/api/ping"}
        )
        assert result is True


class TestHttpAdapterCollectUsage:
    async def test_collect_usage_returns_zeros(self):
        adapter = HttpAdapter()
        report = await adapter.collect_usage(None)
        assert report.tokens_used == 0
        assert report.cost_usd == 0.0
