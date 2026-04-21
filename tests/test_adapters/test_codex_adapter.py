"""Tests for CodexAdapter — TDD red phase."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.adapter_base import AdapterRequest, SessionMode
from nexus.adapters.codex_adapter import CodexAdapter


def _make_request(**kwargs) -> AdapterRequest:
    defaults = {
        "agent_id": "test-agent",
        "agent_profile": "/tmp/profile",
        "work_item_id": 1,
        "work_type": "code",
        "priority": "P2",
        "prompt_context": "Find all TODOs in src/",
        "timeout_seconds": 30,
        "correlation_id": "corr-abc-123",
    }
    defaults.update(kwargs)
    return AdapterRequest(**defaults)


def _make_proc(
    returncode: int = 0, stdout: bytes = b"result output", stderr: bytes = b""
) -> AsyncMock:
    proc = AsyncMock()
    proc.pid = 12345
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.send_signal = MagicMock()
    return proc


class TestInvokeHeartbeat:
    async def test_happy_path(self):
        """elapsed < timeout, exit 0, stdout has content → succeeded."""
        request = _make_request(timeout_seconds=30)
        proc = _make_proc(returncode=0, stdout=b"found 3 TODOs")

        with (
            patch("nexus.adapters.codex_adapter.asyncio.create_subprocess_exec", return_value=proc),
            patch("nexus.adapters.codex_adapter.time.monotonic", side_effect=[0.0, 5.0]),
        ):
            adapter = CodexAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "succeeded"
        assert result.stdout_excerpt == "found 3 TODOs"
        assert result.usage is not None
        assert result.usage.tokens_used == len("found 3 TODOs") // 4
        assert result.usage.cost_usd == 0.0
        assert result.exit_code == 0

    async def test_timeout_detection_exit_0(self):
        """Critical: elapsed >= timeout AND exit code 0 → timed_out (Codex exits 0 on SIGTERM)."""
        request = _make_request(timeout_seconds=30)
        proc = _make_proc(returncode=0, stdout=b"partial output")

        with (
            patch("nexus.adapters.codex_adapter.asyncio.create_subprocess_exec", return_value=proc),
            # elapsed = 30.0 - 0.0 = 30.0, which equals timeout_seconds
            patch("nexus.adapters.codex_adapter.time.monotonic", side_effect=[0.0, 30.0]),
        ):
            adapter = CodexAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "timed_out"
        assert result.exit_code == 0  # confirms we don't rely on exit code

    async def test_normal_failure(self):
        """elapsed < timeout, exit 1 → failed."""
        request = _make_request(timeout_seconds=30)
        proc = _make_proc(returncode=1, stdout=b"", stderr=b"command not found")

        with (
            patch("nexus.adapters.codex_adapter.asyncio.create_subprocess_exec", return_value=proc),
            patch("nexus.adapters.codex_adapter.time.monotonic", side_effect=[0.0, 2.0]),
        ):
            adapter = CodexAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "failed"
        assert result.exit_code == 1
        assert result.stderr_excerpt == "command not found"

    async def test_spawn_error_wrapped(self):
        """OSError during subprocess spawn → AdapterResult with status=failed, error_code=SPAWN_ERROR."""
        request = _make_request()

        with (
            patch(
                "nexus.adapters.codex_adapter.asyncio.create_subprocess_exec",
                side_effect=OSError("No such file"),
            ),
            patch("nexus.adapters.codex_adapter.time.monotonic", return_value=0.0),
        ):
            adapter = CodexAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "failed"
        assert result.error_code == "SPAWN_ERROR"
        assert "No such file" in (result.error_message or "")


class TestResumeSession:
    async def test_raises_not_implemented(self):
        """Codex has no session model — resume_session must raise NotImplementedError."""
        adapter = CodexAdapter()
        request = _make_request()
        with pytest.raises(NotImplementedError, match="session"):
            await adapter.resume_session(request)


class TestValidateEnvironment:
    async def test_codex_not_found(self):
        """shutil.which('codex') returns None → ValidationResult(ok=False)."""
        adapter = CodexAdapter()
        with patch("nexus.adapters.codex_adapter.shutil.which", return_value=None):
            result = await adapter.validate_environment({})
        assert result.ok is False
        assert len(result.errors) > 0

    async def test_codex_found(self):
        """shutil.which('codex') returns a path → ValidationResult(ok=True)."""
        adapter = CodexAdapter()
        with patch(
            "nexus.adapters.codex_adapter.shutil.which", return_value="/usr/local/bin/codex"
        ):
            result = await adapter.validate_environment({})
        assert result.ok is True


class TestDescribe:
    async def test_describe_returns_correct_shape(self):
        adapter = CodexAdapter()
        desc = await adapter.describe()
        assert desc.adapter_id == "codex-cli"
        assert desc.execution_mode == "subprocess"
        assert desc.session_mode == SessionMode.EPHEMERAL
        assert "code" in desc.capabilities


class TestHealthcheck:
    async def test_returns_true_on_exit_0(self):
        proc = _make_proc(returncode=0, stdout=b"codex 1.0.0")
        with patch(
            "nexus.adapters.codex_adapter.asyncio.create_subprocess_exec", return_value=proc
        ):
            adapter = CodexAdapter()
            ok = await adapter.healthcheck({})
        assert ok is True

    async def test_returns_false_on_exit_nonzero(self):
        proc = _make_proc(returncode=1)
        with patch(
            "nexus.adapters.codex_adapter.asyncio.create_subprocess_exec", return_value=proc
        ):
            adapter = CodexAdapter()
            ok = await adapter.healthcheck({})
        assert ok is False

    async def test_returns_false_when_codex_absent(self):
        with patch(
            "nexus.adapters.codex_adapter.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            adapter = CodexAdapter()
            ok = await adapter.healthcheck({})
        assert ok is False


class TestCollectUsage:
    async def test_returns_usage_report(self):
        adapter = CodexAdapter()
        report = await adapter.collect_usage({"tokens_used": 42})
        assert report.tokens_used == 42
        assert report.cost_usd == 0.0

    async def test_missing_tokens_defaults_to_zero(self):
        adapter = CodexAdapter()
        report = await adapter.collect_usage({})
        assert report.tokens_used == 0
