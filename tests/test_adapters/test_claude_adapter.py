"""Tests for ClaudeAdapter — TDD red phase."""

from __future__ import annotations

import asyncio
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

from nexus.adapter_base import AdapterRequest, AdapterResult
from nexus.adapters.claude_adapter import ClaudeAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_JSON_ENVELOPE = json.dumps(
    {
        "result": "Task complete.",
        "session_id": "sess-abc123",
        "cost_usd": 0.0045,
        "usage": {
            "input_tokens": 500,
            "output_tokens": 150,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
)


def _make_request(tmp_profile: pathlib.Path, **kwargs) -> AdapterRequest:
    defaults = {
        "agent_id": "agent-test",
        "agent_profile": str(tmp_profile),
        "work_item_id": 1,
        "work_type": "code",
        "priority": "P2",
        "prompt_context": "Do something useful.",
        "timeout_seconds": 60,
        "correlation_id": "corr-001",
        "session_ref": None,
    }
    defaults.update(kwargs)
    return AdapterRequest(**defaults)


def _mock_proc(returncode: int, stdout: str, stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    return proc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInvokeHeartbeat:
    async def test_happy_path(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(0, VALID_JSON_ENVELOPE)
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(_make_request(tmp_profile_path))

        assert result.status == "succeeded"
        assert result.usage is not None
        assert result.usage.tokens_used == 650  # 500 + 150
        assert result.session_after == "sess-abc123"
        assert result.result_payload.get("output") == "Task complete."

    async def test_timeout_path(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(0, VALID_JSON_ENVELOPE)
        # communicate() raises TimeoutError
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(_make_request(tmp_profile_path))

        assert result.status == "timed_out"
        proc.terminate.assert_called_once()

    async def test_session_resume_passes_session_id(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(0, VALID_JSON_ENVELOPE)
        captured_args: list[str] = []

        async def capture_exec(*args, **kwargs):
            captured_args.extend(args)
            return proc

        with patch("asyncio.create_subprocess_exec", new=capture_exec):
            adapter = ClaudeAdapter()
            await adapter.invoke_heartbeat(_make_request(tmp_profile_path, session_ref="abc123"))

        assert "--session-id" in captured_args
        idx = captured_args.index("--session-id")
        assert captured_args[idx + 1] == "abc123"

    async def test_malformed_json(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(0, "not json at all")
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(_make_request(tmp_profile_path))

        assert result.status == "failed"
        assert result.error_code == "PARSE_ERROR"

    async def test_nonzero_exit(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(1, "", "something went wrong in claude cli")
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(_make_request(tmp_profile_path))

        assert result.status == "failed"
        assert result.error_message is not None
        assert "something went wrong in claude cli" in result.error_message


class TestResumeSession:
    async def test_resume_passes_session_id(self, tmp_profile_path: pathlib.Path) -> None:
        proc = _mock_proc(0, VALID_JSON_ENVELOPE)
        captured_args: list[str] = []

        async def capture_exec(*args, **kwargs):
            captured_args.extend(args)
            return proc

        with patch("asyncio.create_subprocess_exec", new=capture_exec):
            adapter = ClaudeAdapter()
            await adapter.resume_session(_make_request(tmp_profile_path, session_ref="resume-xyz"))

        assert "--session-id" in captured_args
        idx = captured_args.index("--session-id")
        assert captured_args[idx + 1] == "resume-xyz"


class TestValidateEnvironment:
    async def test_claude_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            adapter = ClaudeAdapter()
            result = await adapter.validate_environment({})

        assert result.ok is False
        assert len(result.errors) > 0

    async def test_claude_found(self) -> None:
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            adapter = ClaudeAdapter()
            result = await adapter.validate_environment({})

        assert result.ok is True


class TestHealthcheck:
    async def test_healthcheck_ok(self) -> None:
        proc = _mock_proc(0, "claude 1.0.0")
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            ok = await adapter.healthcheck({})
        assert ok is True

    async def test_healthcheck_fails(self) -> None:
        proc = _mock_proc(1, "")
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            adapter = ClaudeAdapter()
            ok = await adapter.healthcheck({})
        assert ok is False


class TestDescribe:
    async def test_describe_returns_adapter_id(self) -> None:
        adapter = ClaudeAdapter()
        desc = await adapter.describe()
        assert desc.adapter_id == "claude-code-cli"
        assert desc.session_mode == "resumable"
        assert "code" in desc.capabilities


class TestCollectUsage:
    async def test_collect_usage_from_result(self) -> None:
        adapter = ClaudeAdapter()
        result = AdapterResult(
            status="succeeded",
            started_at="2026-04-20T10:00:00",
            finished_at="2026-04-20T10:00:05",
            usage=None,
            result_payload={
                "_tokens_input": 400,
                "_tokens_output": 100,
                "_cost_usd": 0.002,
            },
        )
        usage = await adapter.collect_usage(result)
        assert usage.tokens_used == 500
        assert usage.cost_usd == 0.002
