"""Local SDK helpers for ClaudeAdapter — patch, stderr filter, error classifier, prompt reader.

These are module-level utilities that ClaudeAdapter needs. Not a library extraction.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK message-parser patch — lenient unknown event handling
# ---------------------------------------------------------------------------

_PATCHED = False


def _patch_sdk_message_parser() -> None:
    """Patch SDK parse_message to skip unknown event types instead of crashing.

    The Anthropic CLI emits rate_limit_event as a streaming event. Older SDK
    versions don't handle it and raise MessageParseError. This patch returns
    None for unknown types so the async generator continues.
    """
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    try:
        import claude_agent_sdk._internal.client as _client
        import claude_agent_sdk._internal.message_parser as _mp
        from claude_agent_sdk._errors import MessageParseError as _MPE

        _original = _mp.parse_message

        def _lenient_parse(data: dict[str, Any]) -> object:
            try:
                return _original(data)
            except _MPE as exc:
                if "Unknown message type" in str(exc):
                    logger.debug("Skipping unknown SDK event type '%s'", data.get("type", "?"))
                    return None
                raise

        _mp.parse_message = _lenient_parse  # type: ignore[assignment]  # narrower signature than protocol
        if hasattr(_client, "parse_message"):
            _client.parse_message = _lenient_parse
    except Exception:
        logger.debug("Could not patch SDK message parser", exc_info=True)


# Apply patch at import time.
_patch_sdk_message_parser()

# ---------------------------------------------------------------------------
# stderr filter
# ---------------------------------------------------------------------------

_stderr_stream_closed_seen = False


def _stderr_handler(line: str) -> None:
    """Filter and log CLI stderr lines — suppress noise from bundled CLI."""
    global _stderr_stream_closed_seen
    stripped = line.strip()
    if not stripped:
        return
    if len(stripped) > 500:
        logger.debug("CLI stderr: [truncated %d chars]", len(stripped))
        return
    if stripped.startswith("Error in hook callback"):
        logger.debug("CLI stderr: hook callback error")
        return
    if "Stream closed" in stripped:
        if _stderr_stream_closed_seen:
            logger.debug("CLI stderr: %s", stripped)
        else:
            _stderr_stream_closed_seen = True
            logger.warning("CLI stderr: %s", stripped)
        return
    logger.warning("CLI stderr: %s", stripped)


# ---------------------------------------------------------------------------
# Transient error classifier
# ---------------------------------------------------------------------------

_TRANSIENT_DELAY = 5  # seconds


def _is_transient(exc: BaseException) -> int | None:
    """Return retry delay (seconds) for known transient SDK errors, else None."""
    msg = str(exc)
    if "Control request timeout: initialize" in msg:
        return _TRANSIENT_DELAY
    try:
        from claude_agent_sdk._errors import MessageParseError

        if isinstance(exc, MessageParseError) and "rate_limit_event" in msg:
            return _TRANSIENT_DELAY
    except Exception:
        pass
    return None


# System prompt reader moved to shared _profile module (imported by ClaudeAdapter directly).
