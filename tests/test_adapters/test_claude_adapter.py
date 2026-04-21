"""Tests for ClaudeAdapter — SDK-based implementation."""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch  # noqa: F401

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import TextBlock

from nexus.adapter_base import AdapterRequest, AdapterResult
from nexus.adapters.claude_adapter import ClaudeAdapter

# ---------------------------------------------------------------------------
# SDK message factories
# ---------------------------------------------------------------------------


def _assistant_msg(text: str, model: str = "claude-sonnet-4-6") -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text)], model=model)


def _result_msg(
    session_id: str = "s1",
    usage: dict[str, Any] | None = None,
    total_cost_usd: float = 0.0045,
) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1234,
        duration_api_ms=1000,
        is_error=False,
        num_turns=1,
        session_id=session_id,
        total_cost_usd=total_cost_usd,
        usage=usage
        or {
            "input_tokens": 500,
            "output_tokens": 150,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 20,
        },
    )


async def _sdk_gen(*msgs: Any) -> AsyncIterator[Any]:
    """Async generator helper that yields pre-canned messages."""
    for m in msgs:
        yield m


def _make_request(tmp_profile: pathlib.Path, **kwargs: Any) -> AdapterRequest:
    defaults: dict[str, Any] = {
        "agent_id": "agent-test",
        "agent_profile": str(tmp_profile / "CLAUDE.md"),
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


# ---------------------------------------------------------------------------
# conftest-style fixture — profile path for adapter tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def profile(tmp_path: pathlib.Path) -> pathlib.Path:
    """CLAUDE.md with fenced YAML front-matter + body."""
    d = tmp_path / "agent-profile"
    d.mkdir()
    (d / "CLAUDE.md").write_text(
        "```yaml\nagent_role: test\nmodel: claude-sonnet-4-6\n```\n\n# Test Agent\n\nYou are a test agent.\n"
    )
    return d


# ---------------------------------------------------------------------------
# Helper: captured ClaudeAgentOptions
# ---------------------------------------------------------------------------


def _capture_opts_side_effect(captured: dict[str, Any]):
    """Return a side_effect that saves the options kwarg and yields canned messages."""

    async def _gen(prompt: str, options: Any) -> AsyncIterator[Any]:
        captured["options"] = options
        yield _assistant_msg("ok")
        yield _result_msg()

    return _gen


# ---------------------------------------------------------------------------
# TestInvokeHeartbeat
# ---------------------------------------------------------------------------


class TestInvokeHeartbeat:
    async def test_happy_path(self, profile: pathlib.Path) -> None:
        """SDK yields AssistantMessage + ResultMessage → status=succeeded."""

        async def _fake_query(prompt: str, options: Any) -> AsyncIterator[Any]:
            yield _assistant_msg("Task complete.")
            yield _result_msg(session_id="sess-abc123", total_cost_usd=0.0045)

        with patch("nexus.adapters.claude_adapter.query", side_effect=_fake_query):
            result = await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "succeeded"
        assert result.result_payload.get("output") == "Task complete."
        assert result.session_after == "sess-abc123"
        assert result.usage is not None
        assert result.usage.tokens_used == 650  # 500 + 150

    async def test_model_forwarding(self, profile: pathlib.Path) -> None:
        """extra['model'] is forwarded to ClaudeAgentOptions.model."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(
                _make_request(profile, extra={"model": "claude-opus-4-7"})
            )

        assert captured["options"].model == "claude-opus-4-7"

    async def test_tools_forwarding(self, profile: pathlib.Path) -> None:
        """tools_allowlist is forwarded to ClaudeAgentOptions.allowed_tools."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(
                _make_request(profile, tools_allowlist=["Read", "Bash"])
            )

        assert captured["options"].allowed_tools == ["Read", "Bash"]

    async def test_tools_empty_defaults_to_minimal_safe_set(self, profile: pathlib.Path) -> None:
        """Empty tools_allowlist defaults to minimal safe set."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        allowed = captured["options"].allowed_tools
        assert "Read" in allowed
        assert "Glob" in allowed
        assert "Grep" in allowed

    async def test_max_turns_forwarding(self, profile: pathlib.Path) -> None:
        """extra['max_turns'] is forwarded to ClaudeAgentOptions.max_turns."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(_make_request(profile, extra={"max_turns": 80}))

        assert captured["options"].max_turns == 80

    async def test_resume_forwarded(self, profile: pathlib.Path) -> None:
        """session_ref is forwarded as ClaudeAgentOptions.resume."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            result = await ClaudeAdapter().invoke_heartbeat(
                _make_request(profile, session_ref="s0")
            )

        assert captured["options"].resume == "s0"
        assert result.session_before == "s0"

    async def test_timeout(self, profile: pathlib.Path) -> None:
        """query that sleeps beyond timeout → status=timed_out."""

        async def _slow_query(prompt: str, options: Any) -> AsyncIterator[Any]:
            await asyncio.sleep(10)
            yield _assistant_msg("too late")

        with patch("nexus.adapters.claude_adapter.query", side_effect=_slow_query):
            result = await ClaudeAdapter().invoke_heartbeat(
                _make_request(profile, timeout_seconds=1)
            )

        assert result.status == "timed_out"

    async def test_permission_mode_always_bypass(self, profile: pathlib.Path) -> None:
        """permission_mode is always bypassPermissions."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        assert captured["options"].permission_mode == "bypassPermissions"

    async def test_retry_on_transient(self, profile: pathlib.Path) -> None:
        """First call raises transient error → retried once → succeeds."""
        calls: list[int] = []

        async def _flaky_query(prompt: str, options: Any) -> AsyncIterator[Any]:
            calls.append(1)
            if len(calls) == 1:
                raise Exception("Control request timeout: initialize")
            yield _assistant_msg("ok after retry")
            yield _result_msg()

        with (
            patch("nexus.adapters.claude_adapter.query", side_effect=_flaky_query),
            patch("nexus.adapters.claude_adapter.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            result = await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "succeeded"
        assert len(calls) == 2
        mock_sleep.assert_called_once_with(5)

    async def test_retry_exhausted(self, profile: pathlib.Path) -> None:
        """Both attempts raise transient error → status=failed, TRANSIENT_EXHAUSTED."""

        async def _always_fail(prompt: str, options: Any) -> AsyncIterator[Any]:
            raise Exception("Control request timeout: initialize")
            yield  # make it a generator

        with (
            patch("nexus.adapters.claude_adapter.query", side_effect=_always_fail),
            patch("nexus.adapters.claude_adapter.asyncio.sleep", new=AsyncMock()),
        ):
            result = await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "failed"
        assert result.error_code == "TRANSIENT_EXHAUSTED"

    async def test_non_transient_exception(self, profile: pathlib.Path) -> None:
        """Non-transient exception → status=failed, SDK_ERROR."""

        async def _bad_query(prompt: str, options: Any) -> AsyncIterator[Any]:
            raise RuntimeError("some unexpected sdk bug")
            yield

        with patch("nexus.adapters.claude_adapter.query", side_effect=_bad_query):
            result = await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "failed"
        assert result.error_code == "SDK_ERROR"

    async def test_system_prompt_reads_file_body(self, profile: pathlib.Path) -> None:
        """agent_profile path → ClaudeAgentOptions.system_prompt is the body text, not the path."""
        captured: dict[str, Any] = {}

        with patch(
            "nexus.adapters.claude_adapter.query",
            side_effect=_capture_opts_side_effect(captured),
        ):
            await ClaudeAdapter().invoke_heartbeat(_make_request(profile))

        sp = captured["options"].system_prompt
        assert isinstance(sp, str)
        assert "Test Agent" in sp
        assert "agent_role" not in sp
        assert str(profile) not in sp


# ---------------------------------------------------------------------------
# TestValidateEnvironment
# ---------------------------------------------------------------------------


class TestValidateEnvironment:
    async def test_sdk_importable(self) -> None:
        """SDK importable → validate_environment returns ok=True."""
        result = await ClaudeAdapter().validate_environment({})
        assert result.ok is True

    async def test_sdk_not_importable(self) -> None:
        """SDK not importable → validate_environment returns ok=False."""
        with patch.dict("sys.modules", {"claude_agent_sdk": None}):  # type: ignore[dict-item]
            result = await ClaudeAdapter().validate_environment({})
        assert result.ok is False


# ---------------------------------------------------------------------------
# TestHealthcheck
# ---------------------------------------------------------------------------


class TestHealthcheck:
    async def test_healthcheck_ok_when_sdk_importable(self) -> None:
        result = await ClaudeAdapter().healthcheck({})
        assert result is True


# ---------------------------------------------------------------------------
# TestDescribe
# ---------------------------------------------------------------------------


class TestDescribe:
    async def test_describe_returns_adapter_id(self) -> None:
        desc = await ClaudeAdapter().describe()
        assert desc.adapter_id == "claude-code-cli"
        assert desc.session_mode == "resumable"
        assert "code" in desc.capabilities


# ---------------------------------------------------------------------------
# TestCollectUsage
# ---------------------------------------------------------------------------


class TestCollectUsage:
    async def test_collect_usage_from_result(self) -> None:
        result = AdapterResult(
            status="succeeded",
            started_at="2026-04-20T10:00:00",
            finished_at="2026-04-20T10:00:05",
            result_payload={
                "_tokens_input": 400,
                "_tokens_output": 100,
                "_cost_usd": 0.002,
            },
        )
        usage = await ClaudeAdapter().collect_usage(result)
        assert usage.tokens_used == 500
        assert usage.cost_usd == 0.002


# ---------------------------------------------------------------------------
# TestResumeSession
# ---------------------------------------------------------------------------


class TestResumeSession:
    async def test_resume_session_delegates_to_run(self, profile: pathlib.Path) -> None:
        """resume_session calls _run with same semantics as invoke_heartbeat."""

        async def _fake_query(prompt: str, options: Any) -> AsyncIterator[Any]:
            yield _assistant_msg("resumed")
            yield _result_msg(session_id="new-sess")

        with patch("nexus.adapters.claude_adapter.query", side_effect=_fake_query):
            result = await ClaudeAdapter().resume_session(
                _make_request(profile, session_ref="old-sess")
            )

        assert result.status == "succeeded"
        assert result.session_before == "old-sess"
        assert result.session_after == "new-sess"
