"""Tests for ProcessAdapter — TDD red phase written before implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.adapter_base import AdapterRequest, SessionMode
from nexus.adapters.process_adapter import ProcessAdapter


def make_request(**overrides) -> AdapterRequest:
    defaults = {
        "agent_id": "test-agent",
        "agent_profile": "test-profile",
        "work_item_id": 1,
        "work_type": "test",
        "priority": "P2",
        "prompt_context": "do the thing",
        "timeout_seconds": 30,
        "correlation_id": "corr-123",
        "extra": {
            "executable": "/usr/bin/echo",
            "args": ["hello"],
            "stdin_mode": "prompt",
        },
    }
    defaults.update(overrides)
    return AdapterRequest(**defaults)


def make_proc(returncode: int = 0, stdout: bytes = b"ok", stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.pid = 42
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.send_signal = MagicMock()
    proc.wait = AsyncMock()
    return proc


class TestProcessAdapterDescribe:
    async def test_describe_returns_ephemeral(self):
        adapter = ProcessAdapter()
        desc = await adapter.describe()
        assert desc.adapter_id == "process"
        assert desc.session_mode == SessionMode.EPHEMERAL
        assert desc.execution_mode == "subprocess"
        assert "local-exec" in desc.capabilities


class TestProcessAdapterResumeSession:
    async def test_resume_session_raises(self):
        adapter = ProcessAdapter()
        request = make_request()
        with pytest.raises(NotImplementedError):
            await adapter.resume_session(request)


class TestProcessAdapterHealthcheck:
    async def test_healthcheck_returns_true(self):
        adapter = ProcessAdapter()
        result = await adapter.healthcheck({})
        assert result is True


class TestProcessAdapterCollectUsage:
    async def test_collect_usage_returns_zeros(self):
        adapter = ProcessAdapter()
        report = await adapter.collect_usage(None)
        assert report.tokens_used == 0
        assert report.cost_usd == 0.0


class TestProcessAdapterValidateEnvironment:
    async def test_missing_executable_returns_not_ok(self):
        adapter = ProcessAdapter()
        with patch("shutil.which", return_value=None):
            result = await adapter.validate_environment({"executable": "no-such-binary"})
        assert result.ok is False
        assert result.errors

    async def test_not_executable_returns_not_ok(self, tmp_path):
        adapter = ProcessAdapter()
        script = tmp_path / "script.sh"
        script.write_text("#!/bin/sh\necho hi")
        # exists but not executable
        with (
            patch("shutil.which", return_value=str(script)),
            patch("os.access", return_value=False),
        ):
            result = await adapter.validate_environment({"executable": str(script)})
        assert result.ok is False
        assert result.errors

    async def test_valid_executable_returns_ok(self):
        adapter = ProcessAdapter()
        with (
            patch("shutil.which", return_value="/usr/bin/echo"),
            patch("os.access", return_value=True),
        ):
            result = await adapter.validate_environment({"executable": "echo"})
        assert result.ok is True
        assert result.errors == []


class TestProcessAdapterInvokeHeartbeat:
    async def test_happy_path_exit_zero(self):
        adapter = ProcessAdapter()
        request = make_request()
        proc = make_proc(returncode=0, stdout=b"output line\n")

        with (
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
            patch("shutil.which", return_value="/usr/bin/echo"),
        ):
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "succeeded"
        assert result.exit_code == 0
        # stdin must have been the encoded prompt
        call_kwargs = proc.communicate.call_args
        assert call_kwargs.kwargs.get("input") == request.prompt_context.encode()

    async def test_exit_one_returns_failed(self):
        adapter = ProcessAdapter()
        request = make_request()
        proc = make_proc(returncode=1, stderr=b"error")

        with (
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
            patch("shutil.which", return_value="/usr/bin/echo"),
        ):
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "failed"
        assert result.exit_code == 1

    async def test_exit_139_segfault_returns_failed(self):
        adapter = ProcessAdapter()
        request = make_request()
        proc = make_proc(returncode=139, stderr=b"Segmentation fault")

        with (
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
            patch("shutil.which", return_value="/usr/bin/echo"),
        ):
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "failed"
        assert result.exit_code == 139

    async def test_timeout_returns_timed_out_and_sigterm(self):
        adapter = ProcessAdapter()
        request = make_request()
        proc = MagicMock()
        proc.pid = 42
        proc.communicate = AsyncMock(side_effect=TimeoutError())
        proc.send_signal = MagicMock()
        proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
            patch("shutil.which", return_value="/usr/bin/echo"),
            patch("os.killpg", MagicMock()),
            patch("os.getpgid", return_value=42),
        ):
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "timed_out"

    async def test_stdin_mode_none_passes_no_input(self):
        adapter = ProcessAdapter()
        request = make_request(
            extra={"executable": "/usr/bin/cat", "args": [], "stdin_mode": "none"}
        )
        proc = make_proc(returncode=0)

        with (
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
            patch("shutil.which", return_value="/usr/bin/cat"),
        ):
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "succeeded"
        call_kwargs = proc.communicate.call_args
        assert call_kwargs.kwargs.get("input") is None
