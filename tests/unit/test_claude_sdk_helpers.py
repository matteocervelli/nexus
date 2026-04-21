"""Tests for _claude_sdk.py helper functions — TDD red phase."""

from __future__ import annotations

import logging
import pathlib

import pytest

from nexus.adapters._claude_sdk import (
    _is_transient,
    _read_system_prompt,
    _stderr_handler,
)

# ---------------------------------------------------------------------------
# _read_system_prompt
# ---------------------------------------------------------------------------


def test_read_system_prompt_fenced(tmp_path: pathlib.Path) -> None:
    """Backtick-fenced YAML block is stripped; markdown body returned."""
    md = tmp_path / "CLAUDE.md"
    md.write_text(
        "```yaml\nagent_role: test\nmodel: claude-sonnet-4-6\n```\n\n# Identity\n\nYou are a test agent.\n"
    )
    body = _read_system_prompt(str(md))
    assert "# Identity" in body
    assert "You are a test agent." in body
    assert "```yaml" not in body
    assert "agent_role" not in body


def test_read_system_prompt_delimiter(tmp_path: pathlib.Path) -> None:
    """Triple-dash front-matter block is stripped; markdown body returned."""
    md = tmp_path / "CLAUDE.md"
    md.write_text(
        "---\nagent_role: test\nmodel: claude-sonnet-4-6\n---\n\n# Identity\n\nYou are a test agent.\n"
    )
    body = _read_system_prompt(str(md))
    assert "# Identity" in body
    assert "You are a test agent." in body
    assert "---" not in body
    assert "agent_role" not in body


def test_read_system_prompt_no_frontmatter(tmp_path: pathlib.Path) -> None:
    """File with no front-matter returns full content."""
    md = tmp_path / "CLAUDE.md"
    md.write_text("# Agent\n\nYou are an agent.\n")
    body = _read_system_prompt(str(md))
    assert "# Agent" in body
    assert "You are an agent." in body


def test_read_system_prompt_strips_leading_whitespace(tmp_path: pathlib.Path) -> None:
    """Body after stripping front-matter has leading whitespace removed."""
    md = tmp_path / "CLAUDE.md"
    md.write_text("```yaml\nk: v\n```\n\n\n# Body\n")
    body = _read_system_prompt(str(md))
    assert not body.startswith("\n")


# ---------------------------------------------------------------------------
# _is_transient
# ---------------------------------------------------------------------------


def test_is_transient_init_timeout() -> None:
    """Control request timeout returns retry delay of 5."""
    exc = Exception("Control request timeout: initialize")
    delay = _is_transient(exc)
    assert delay == 5


def test_is_transient_rate_limit_parse_error() -> None:
    """MessageParseError with rate_limit_event returns retry delay."""
    from claude_agent_sdk._errors import MessageParseError

    exc = MessageParseError("Unknown message type: rate_limit_event")
    delay = _is_transient(exc)
    assert delay == 5


def test_is_transient_other_exception() -> None:
    """Generic exceptions return None (not transient)."""
    assert _is_transient(RuntimeError("something bad")) is None


def test_is_transient_value_error() -> None:
    """ValueError without relevant text returns None."""
    assert _is_transient(ValueError("bad input")) is None


# ---------------------------------------------------------------------------
# _stderr_handler
# ---------------------------------------------------------------------------


def test_stderr_handler_empty_line(caplog: pytest.LogCaptureFixture) -> None:
    """Empty line produces no log output."""
    with caplog.at_level(logging.DEBUG):
        _stderr_handler("")
    assert caplog.records == []


def test_stderr_handler_long_line_goes_to_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Lines >500 chars are downgraded to DEBUG."""
    long_line = "x" * 501
    with caplog.at_level(logging.DEBUG):
        _stderr_handler(long_line)
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_stderr_handler_hook_callback_error_debug(caplog: pytest.LogCaptureFixture) -> None:
    """'Error in hook callback' lines go to DEBUG."""
    with caplog.at_level(logging.DEBUG):
        _stderr_handler("Error in hook callback: something happened")
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_stderr_handler_stream_closed_first_is_warning(caplog: pytest.LogCaptureFixture) -> None:
    """First 'Stream closed' line is WARNING."""
    # Reset global state before test
    import nexus.adapters._claude_sdk as _sdk_mod

    _sdk_mod._stderr_stream_closed_seen = False
    with caplog.at_level(logging.WARNING):
        _stderr_handler("Stream closed unexpectedly")
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_stderr_handler_stream_closed_repeat_is_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Repeated 'Stream closed' lines are downgraded to DEBUG."""
    import nexus.adapters._claude_sdk as _sdk_mod

    _sdk_mod._stderr_stream_closed_seen = True  # already seen once
    with caplog.at_level(logging.DEBUG):
        _stderr_handler("Stream closed unexpectedly")
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
    # Reset for other tests
    _sdk_mod._stderr_stream_closed_seen = False


def test_stderr_handler_normal_line_is_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Normal lines under 500 chars are emitted at WARNING."""
    with caplog.at_level(logging.WARNING):
        _stderr_handler("Some unexpected CLI error message")
    assert any(r.levelno == logging.WARNING for r in caplog.records)
