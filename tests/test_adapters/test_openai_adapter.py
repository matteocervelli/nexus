"""Tests for CodexAdapter — openai_codex_sdk-based implementation."""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai_codex_sdk import (
    AgentMessageItem,
    ItemCompletedEvent,
    ThreadErrorEvent,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    Usage,
)
from openai_codex_sdk.errors import CodexExecError

from nexus.adapter_base import AdapterRequest, AdapterResult, SessionMode
from nexus.adapters.openai_adapter import CodexAdapter

# ---------------------------------------------------------------------------
# Fake event stream helpers
# ---------------------------------------------------------------------------


async def _fake_events(
    text: str = "Task complete.",
    in_tok: int = 100,
    out_tok: int = 50,
    thread_id: str = "thread-abc",
):
    """Async generator that yields a minimal happy-path event sequence."""
    yield ThreadStartedEvent(type="thread.started", thread_id=thread_id)
    yield ItemCompletedEvent(
        type="item.completed",
        item=AgentMessageItem(id="item-1", type="agent_message", text=text),
    )
    yield TurnCompletedEvent(
        type="turn.completed",
        usage=Usage(input_tokens=in_tok, cached_input_tokens=0, output_tokens=out_tok),
    )


def _mock_codex(
    text: str = "Task complete.",
    in_tok: int = 100,
    out_tok: int = 50,
    thread_id: str = "thread-abc",
) -> MagicMock:
    """Return a mock Codex instance with a thread that streams fake events."""
    streamed = MagicMock()
    streamed.events = _fake_events(text, in_tok, out_tok, thread_id)

    thread = MagicMock()
    thread.run_streamed = AsyncMock(return_value=streamed)
    thread.id = thread_id

    codex = MagicMock()
    codex.start_thread = MagicMock(return_value=thread)
    codex.resume_thread = MagicMock(return_value=thread)
    return codex


# ---------------------------------------------------------------------------
# Request factory
# ---------------------------------------------------------------------------


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
    }
    defaults.update(kwargs)
    return AdapterRequest(**defaults)


@pytest.fixture()
def profile(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "agent-profile"
    d.mkdir()
    (d / "CLAUDE.md").write_text(
        "```yaml\nagent_role: test\nmodel: gpt-4o\n```\n\n# Test Agent\n\nYou are a test agent.\n"
    )
    return d


# ---------------------------------------------------------------------------
# TestInvokeHeartbeat
# ---------------------------------------------------------------------------


class TestInvokeHeartbeat:
    async def test_happy_path(self, profile: pathlib.Path) -> None:
        """Streaming events → status=succeeded, tokens + cost populated."""
        mock = _mock_codex("Task complete.", in_tok=100, out_tok=50)

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "succeeded"
        assert "Task complete." in result.stdout_excerpt
        assert result.result_payload.get("output") == "Task complete."
        assert result.result_payload.get("_tokens_input") == 100
        assert result.result_payload.get("_tokens_output") == 50
        assert result.usage is not None
        assert result.usage.tokens_used == 150
        assert result.usage.cost_usd > 0
        assert result.cost_usd > 0
        assert result.session_after == "thread-abc"

    async def test_model_forwarding(self, profile: pathlib.Path) -> None:
        """extra['model'] is forwarded to start_thread ThreadOptions."""
        mock = _mock_codex()

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            await CodexAdapter().invoke_heartbeat(_make_request(profile, extra={"model": "gpt-4o"}))

        call_kwargs = mock.start_thread.call_args
        opts = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("options", {})
        assert isinstance(opts, dict)
        assert opts.get("model") == "gpt-4o"

    async def test_system_prompt_prepended_to_prompt(self, profile: pathlib.Path) -> None:
        """Agent profile body is prepended to prompt_context (no system message field)."""
        mock = _mock_codex()

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            await CodexAdapter().invoke_heartbeat(
                _make_request(profile, prompt_context="Do the task.")
            )

        run_call = mock.start_thread.return_value.run_streamed.call_args
        prompt_arg = run_call.args[0] if run_call.args else run_call.kwargs.get("input_")
        assert prompt_arg is not None
        assert "Test Agent" in prompt_arg
        assert "Do the task." in prompt_arg

    async def test_timeout_returns_timed_out(self, profile: pathlib.Path) -> None:
        """asyncio.wait_for timeout → status=timed_out, TIMEOUT error_code."""
        mock = _mock_codex()

        async def _slow_run(_prompt: str, **_kwargs: Any):  # type: ignore[override]
            import asyncio

            await asyncio.sleep(999)

        mock.start_thread.return_value.run_streamed = AsyncMock(side_effect=_slow_run)

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().invoke_heartbeat(
                _make_request(profile, timeout_seconds=1)
            )

        assert result.status == "timed_out"
        assert result.error_code == "TIMEOUT"

    async def test_turn_failed_event_returns_failed(self, profile: pathlib.Path) -> None:
        """TurnFailedEvent in stream → status=failed, CODEX_SDK_ERROR."""
        from openai_codex_sdk import ThreadError

        async def _fail_events():
            yield ThreadStartedEvent(type="thread.started", thread_id="t1")
            yield TurnFailedEvent(type="turn.failed", error=ThreadError(message="model overloaded"))

        mock = _mock_codex()
        streamed = MagicMock()
        streamed.events = _fail_events()
        mock.start_thread.return_value.run_streamed = AsyncMock(return_value=streamed)

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "failed"
        assert result.error_code == "CODEX_SDK_ERROR"
        assert "model overloaded" in (result.error_message or "")

    async def test_thread_error_event_returns_failed(self, profile: pathlib.Path) -> None:
        """ThreadErrorEvent in stream → status=failed, CODEX_SDK_ERROR."""

        async def _error_events():
            yield ThreadErrorEvent(type="error", message="binary crashed")

        mock = _mock_codex()
        streamed = MagicMock()
        streamed.events = _error_events()
        mock.start_thread.return_value.run_streamed = AsyncMock(return_value=streamed)

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().invoke_heartbeat(_make_request(profile))

        assert result.status == "failed"
        assert result.error_code == "CODEX_SDK_ERROR"
        assert "binary crashed" in (result.error_message or "")

    async def test_unknown_model_cost_is_zero(self, profile: pathlib.Path) -> None:
        """Unknown model → cost_usd=0.0 (no crash)."""
        mock = _mock_codex(in_tok=100, out_tok=50)

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().invoke_heartbeat(
                _make_request(profile, extra={"model": "gpt-9999-unknown"})
            )

        assert result.status == "succeeded"
        assert result.cost_usd == 0.0
        assert result.usage is not None
        assert result.usage.cost_usd == 0.0


# ---------------------------------------------------------------------------
# TestDescribe
# ---------------------------------------------------------------------------


class TestDescribe:
    async def test_describe_returns_codex_sdk(self) -> None:
        desc = await CodexAdapter().describe()
        assert desc.adapter_id == "codex-sdk"
        assert desc.execution_mode == "subprocess"
        assert desc.session_mode == SessionMode.RESUMABLE
        assert "code" in desc.capabilities
        assert "edit" in desc.capabilities


# ---------------------------------------------------------------------------
# TestValidateEnvironment
# ---------------------------------------------------------------------------


class TestValidateEnvironment:
    async def test_ok_when_sdk_and_binary_present(self) -> None:
        with patch("nexus.adapters.openai_adapter.Codex"):
            result = await CodexAdapter().validate_environment({})
        assert result.ok is True

    async def test_fails_when_sdk_not_importable(self) -> None:
        with patch.dict("sys.modules", {"openai_codex_sdk": None}):  # type: ignore[dict-item]
            result = await CodexAdapter().validate_environment({})
        assert result.ok is False
        assert any("not importable" in e for e in result.errors)

    async def test_fails_when_binary_not_found(self) -> None:
        with patch(
            "nexus.adapters.openai_adapter.Codex",
            side_effect=CodexExecError("codex not found"),
        ):
            result = await CodexAdapter().validate_environment({})
        assert result.ok is False
        assert any("binary not found" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestResumeSession
# ---------------------------------------------------------------------------


class TestResumeSession:
    async def test_resume_uses_resume_thread(self, profile: pathlib.Path) -> None:
        """resume_session calls resume_thread(session_ref) → session_before/after set."""
        mock = _mock_codex(thread_id="resumed-thread")

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            result = await CodexAdapter().resume_session(
                _make_request(profile, session_ref="old-thread-id")
            )

        mock.resume_thread.assert_called_once()
        call_args = mock.resume_thread.call_args
        assert call_args.args[0] == "old-thread-id"

        assert result.status == "succeeded"
        assert result.session_before == "old-thread-id"
        assert result.session_after == "resumed-thread"

    async def test_invoke_heartbeat_uses_start_thread(self, profile: pathlib.Path) -> None:
        """invoke_heartbeat always calls start_thread, not resume_thread."""
        mock = _mock_codex()

        with patch("nexus.adapters.openai_adapter.Codex", return_value=mock):
            await CodexAdapter().invoke_heartbeat(_make_request(profile))

        mock.start_thread.assert_called_once()
        mock.resume_thread.assert_not_called()


# ---------------------------------------------------------------------------
# TestCancelRun
# ---------------------------------------------------------------------------


class TestCancelRun:
    async def test_cancel_run_is_noop(self, profile: pathlib.Path) -> None:
        result = await CodexAdapter().cancel_run(_make_request(profile))
        assert result is None


# ---------------------------------------------------------------------------
# TestCollectUsage
# ---------------------------------------------------------------------------


class TestCollectUsage:
    async def test_collect_usage_from_result_payload(self) -> None:
        result = AdapterResult(
            status="succeeded",
            started_at="2026-04-21T10:00:00+00:00",
            finished_at="2026-04-21T10:00:05+00:00",
            result_payload={
                "_tokens_input": 200,
                "_tokens_output": 80,
                "_cost_usd": 0.00082,
            },
        )
        usage = await CodexAdapter().collect_usage(result)
        assert usage.tokens_used == 280
        assert abs(usage.cost_usd - 0.00082) < 1e-9

    async def test_collect_usage_from_dict(self) -> None:
        usage = await CodexAdapter().collect_usage(
            {"_tokens_input": 50, "_tokens_output": 20, "_cost_usd": 0.0001}
        )
        assert usage.tokens_used == 70


# ---------------------------------------------------------------------------
# TestHealthcheck
# ---------------------------------------------------------------------------


class TestHealthcheck:
    async def test_healthcheck_ok_when_sdk_and_binary_present(self) -> None:
        with patch("nexus.adapters.openai_adapter.Codex"):
            result = await CodexAdapter().healthcheck({})
        assert result is True

    async def test_healthcheck_fails_when_binary_missing(self) -> None:
        with patch(
            "nexus.adapters.openai_adapter.Codex",
            side_effect=CodexExecError("binary not found"),
        ):
            result = await CodexAdapter().healthcheck({})
        assert result is False
