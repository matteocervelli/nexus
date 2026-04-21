"""Headless subprocess validation for the Claude CLI.

These are INTEGRATION tests — they make real API calls and require the CLI
to be installed and authenticated. Run with:

    pytest tests/test_validation/ -v -m integration

Skip in unit test runs:

    pytest tests/ -v -m "not integration"

Empirical findings captured here form the mock baseline for ClaudeAdapter.
See: docs/headless-execution/claude-cli-headless.md
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLAUDE_BIN = shutil.which("claude")

pytestmark = pytest.mark.integration


async def _spawn(
    *args: str,
    env: dict[str, str] | None = None,
    new_session: bool = False,
) -> asyncio.subprocess.Process:
    """Spawn a subprocess with piped stdout/stderr. Args are passed as a list (no shell)."""
    return await asyncio.create_subprocess_exec(  # noqa: S603 — arg list, not shell
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=new_session,
        **({"env": env} if env else {}),
    )


# ---------------------------------------------------------------------------
# Claude CLI tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CLAUDE_BIN, reason="claude CLI not installed")
class TestClaudeHeadless:
    async def test_plain_text_mode_returns_clean_stdout(self) -> None:
        """Plain text mode: stdout is the response, no envelope, no ANSI."""
        proc = await _spawn(CLAUDE_BIN, "-p", "Return exactly the word: nexustest")  # type: ignore[arg-type]
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        assert proc.returncode == 0
        text = stdout.decode()
        assert "\x1b" not in text, "ANSI escape found in plain text output"
        assert stderr == b"", f"Unexpected stderr: {stderr!r}"
        assert "nexustest" in text.lower()

    async def test_json_mode_envelope_shape(self) -> None:
        """--output-format json returns parseable envelope with expected keys."""
        proc = await _spawn(
            CLAUDE_BIN,
            "-p",
            "Reply: ok",
            "--output-format",
            "json",  # type: ignore[arg-type]
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        assert proc.returncode == 0
        assert stderr == b"", f"Unexpected stderr: {stderr!r}"

        data = json.loads(stdout.decode())
        assert data["type"] == "result"
        assert data["subtype"] == "success"
        assert isinstance(data["result"], str)
        assert isinstance(data["session_id"], str)
        assert isinstance(data["total_cost_usd"], float)
        assert isinstance(data["usage"]["input_tokens"], int)
        assert isinstance(data["usage"]["output_tokens"], int)
        assert "\x1b" not in stdout.decode(), "ANSI escape in JSON output"

    async def test_json_mode_no_ansi_in_result_field(self) -> None:
        """result field inside JSON envelope must be plain text."""
        proc = await _spawn(
            CLAUDE_BIN,
            "-p",
            "Say hello in one word",
            "--output-format",
            "json",  # type: ignore[arg-type]
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        data = json.loads(stdout.decode())
        assert "\x1b" not in data["result"]

    async def test_exit_code_zero_on_success(self) -> None:
        proc = await _spawn(CLAUDE_BIN, "-p", "Say: one")  # type: ignore[arg-type]
        await asyncio.wait_for(proc.communicate(), timeout=60)
        assert proc.returncode == 0

    async def test_exit_code_nonzero_on_bad_flag(self) -> None:
        proc = await _spawn(CLAUDE_BIN, "-p", "hello", "--nonexistent-flag-xyz")  # type: ignore[arg-type]
        await asyncio.wait_for(proc.communicate(), timeout=10)
        assert proc.returncode != 0

    async def test_sigterm_produces_143_exit_code(self) -> None:
        """SIGTERM via process group → exit code 143 (128 + SIGTERM=15)."""
        proc = await _spawn(
            CLAUDE_BIN,  # type: ignore[arg-type]
            "-p",
            "Count from 1 to 10000, one per line.",
            new_session=True,
        )
        await asyncio.sleep(2)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        await asyncio.wait_for(proc.communicate(), timeout=5)
        assert proc.returncode == 143, f"Expected 143, got {proc.returncode}"

    async def test_session_resumption_works(self) -> None:
        """--resume <session_id> continues the previous context."""
        proc1 = await _spawn(
            CLAUDE_BIN,  # type: ignore[arg-type]
            "-p",
            "Remember the secret code: NEXUS42",
            "--output-format",
            "json",
        )
        stdout1, _ = await asyncio.wait_for(proc1.communicate(), timeout=60)
        data1 = json.loads(stdout1.decode())
        session_id = data1["session_id"]
        assert session_id

        proc2 = await _spawn(
            CLAUDE_BIN,  # type: ignore[arg-type]
            "-p",
            "What was the secret code?",
            "--resume",
            session_id,
            "--output-format",
            "json",
        )
        stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=60)
        assert proc2.returncode == 0
        data2 = json.loads(stdout2.decode())
        assert "NEXUS42" in data2["result"]

    async def test_system_prompt_applied(self, tmp_profile_path: Path) -> None:
        """--system-prompt overrides default persona. No --profile flag exists in claude CLI."""
        system_prompt = "You are a robot. Always reply with exactly: BEEP BOOP"
        proc = await _spawn(
            CLAUDE_BIN,  # type: ignore[arg-type]
            "-p",
            "Say hello",
            "--system-prompt",
            system_prompt,
            "--output-format",
            "json",
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        assert proc.returncode == 0
        data = json.loads(stdout.decode())
        assert "BEEP" in data["result"] or "BOOP" in data["result"]
