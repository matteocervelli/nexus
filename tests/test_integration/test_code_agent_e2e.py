"""Integration test: Code Agent finds TODOs and returns structured JSON.

Marked @pytest.mark.integration — skipped in normal CI runs.
Uses mocked Atrium HTTP + mocked subprocess (no live claude binary needed).

Run manually:
    uv run pytest tests/test_integration/test_code_agent_e2e.py -v -m integration
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from nexus.adapter_base import AdapterRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_work_item(item_id: int = 1) -> dict:
    return {
        "id": item_id,
        "type": "code-search",
        "agent_role": "code-agent",
        "priority": "P1",
        "status": "pending",
        "context": {
            "repo_path": "/data/dev/services/limen-assistant",
            "query": "find TODOs",
        },
        "result": None,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "token_cost": 0,
    }


AGENT_RESULT_JSON = json.dumps({
    "status": "done",
    "files_modified": [],
    "summary": "Found 3 TODOs across 2 files.",
    "confidence": 0.95,
    "issues_found": 3,
    "findings": [
        {
            "file": "src/limen/bot.py",
            "line": 42,
            "comment": "TODO: add retry logic",
            "issue_title": "Add retry logic to bot event loop",
        },
        {
            "file": "src/limen/bot.py",
            "line": 88,
            "comment": "TODO: handle disconnect gracefully",
            "issue_title": "Handle Telegram disconnect gracefully",
        },
        {
            "file": "src/limen/scheduler.py",
            "line": 15,
            "comment": "FIXME: race condition on shutdown",
            "issue_title": "Fix race condition in scheduler shutdown",
        },
    ],
})


def make_claude_proc(stdout: bytes = AGENT_RESULT_JSON.encode()) -> MagicMock:
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    proc.send_signal = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCodeAgentFindTodosE2E:
    @respx.mock
    async def test_work_item_created_and_dispatched(self):
        """Full pipeline: work_item created → adapter invoked → result parsed."""
        from nexus.adapters.claude_adapter import ClaudeAdapter

        item = make_work_item(item_id=1)

        # Atrium: fetch work_item
        respx.get("http://localhost:8100/work_items/1").mock(
            return_value=httpx.Response(200, json=item)
        )
        # Atrium: patch result
        patch_route = respx.patch("http://localhost:8100/work_items/1").mock(
            return_value=httpx.Response(200, json={})
        )

        request = AdapterRequest(
            agent_id="code-agent-01",
            agent_profile="agents/code-agent/CLAUDE.md",
            work_item_id=1,
            work_type="code-search",
            priority="P1",
            prompt_context="Find all TODOs in /data/dev/services/limen-assistant",
            timeout_seconds=120,
            correlation_id="e2e-test-001",
            extra={"output_format": "json"},
        )

        proc = make_claude_proc()

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)), \
             patch("shutil.which", return_value="/usr/local/bin/claude"):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "succeeded"
        assert result.exit_code == 0

        # stdout must be parseable JSON with required keys
        output = json.loads(result.stdout_excerpt)
        assert output["status"] == "done"
        assert output["issues_found"] > 0
        assert isinstance(output["findings"], list)
        assert len(output["findings"]) == output["issues_found"]

    @respx.mock
    async def test_result_json_contains_required_fields(self):
        """Verify the JSON output contract matches the Code Agent profile spec."""
        from nexus.adapters.claude_adapter import ClaudeAdapter

        request = AdapterRequest(
            agent_id="code-agent-01",
            agent_profile="agents/code-agent/CLAUDE.md",
            work_item_id=2,
            work_type="code-search",
            priority="P2",
            prompt_context="Find all TODOs in /tmp/test-repo",
            timeout_seconds=60,
            correlation_id="e2e-test-002",
        )

        proc = make_claude_proc()

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)), \
             patch("shutil.which", return_value="/usr/local/bin/claude"):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(request)

        output = json.loads(result.stdout_excerpt)
        for field in ("status", "files_modified", "summary", "confidence"):
            assert field in output, f"Missing required field: {field}"

        assert output["status"] in ("done", "failed", "needs_clarification")
        assert 0.0 <= output["confidence"] <= 1.0

    @respx.mock
    async def test_failed_agent_result_is_surfaced(self):
        """When the agent exits nonzero, result.status = failed."""
        from nexus.adapters.claude_adapter import ClaudeAdapter

        proc = make_claude_proc(stdout=b"")
        proc.returncode = 1

        request = AdapterRequest(
            agent_id="code-agent-01",
            agent_profile="agents/code-agent/CLAUDE.md",
            work_item_id=3,
            work_type="code-search",
            priority="P2",
            prompt_context="Intentionally failing task",
            timeout_seconds=30,
            correlation_id="e2e-test-003",
        )

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)), \
             patch("shutil.which", return_value="/usr/local/bin/claude"):
            adapter = ClaudeAdapter()
            result = await adapter.invoke_heartbeat(request)

        assert result.status == "failed"
        assert result.exit_code == 1
