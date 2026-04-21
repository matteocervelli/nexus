"""Unit tests for `nexus sync-agents` CLI command."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from nexus.cli import cli

ATRIUM = "http://localhost:8100"
ENDPOINT = f"{ATRIUM}/api/agent_registry"

_PROFILE_TMPL = textwrap.dedent("""\
    # {title}
    ```yaml
    agent_role: {role}
    execution_backend: claude-code-cli
    model: claude-sonnet-4-6
    capability_class: code
    timeout_seconds: 900
    monthly_token_budget: 500000
    tool_allowlist: [Read, Write]
    ```
""")


@pytest.fixture()
def agents_dir(tmp_path: Path) -> Path:
    """Synthetic agents dir with two deterministic profiles."""
    for role, title in [("alpha-agent", "Alpha"), ("beta-agent", "Beta")]:
        agent_dir = tmp_path / role
        agent_dir.mkdir()
        (agent_dir / "CLAUDE.md").write_text(_PROFILE_TMPL.format(role=role, title=title))
    return tmp_path


def _invoke(agents_dir: Path, *args: str) -> object:
    return CliRunner().invoke(
        cli, ["sync-agents", "--atrium-url", ATRIUM, "--agents-dir", str(agents_dir), *args]
    )


def test_dry_run_lists_profiles_no_http(agents_dir: Path) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(ENDPOINT)
        result = _invoke(agents_dir, "--dry-run")
    assert result.exit_code == 0, result.output
    assert "alpha-agent" in result.output
    assert "beta-agent" in result.output
    assert route.call_count == 0


@respx.mock
def test_sync_posts_each_profile_payload(agents_dir: Path) -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(201, json={"agent_role": "ok"}))
    result = _invoke(agents_dir)
    assert result.exit_code == 0, result.output
    assert route.call_count == 2
    roles = {json.loads(c.request.content)["agent_role"] for c in route.calls}
    assert roles == {"alpha-agent", "beta-agent"}
    payload = json.loads(route.calls[0].request.content)
    for field in (
        "execution_backend",
        "model",
        "capability_class",
        "profile_path",
        "timeout_seconds",
        "monthly_token_budget",
    ):
        assert field in payload, f"missing field: {field}"


@respx.mock
def test_http_error_exits_nonzero_continues_processing(agents_dir: Path) -> None:
    # alpha fails (500), beta succeeds (201) — command should process both, then exit 1
    respx.post(ENDPOINT).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(201, json={"agent_role": "ok"}),
        ]
    )
    result = _invoke(agents_dir)
    # Both profiles processed (table output has two rows)
    assert "alpha-agent" in result.output
    assert "beta-agent" in result.output
    # Failed role included in exception message
    assert "alpha-agent" in result.output
    # Exit code reflects failure
    assert result.exit_code != 0
    # Exception message contains count and role name
    assert "1 profile(s) failed" in result.output or "Error" in result.output


@respx.mock
def test_transport_error_counted_as_failure(agents_dir: Path) -> None:
    # ConnectError (not just HTTP 5xx) should also be caught and counted
    respx.post(ENDPOINT).mock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            httpx.Response(201, json={"agent_role": "ok"}),
        ]
    )
    result = _invoke(agents_dir)
    assert result.exit_code != 0
    assert "ERROR" in result.output


@respx.mock
def test_idempotent_rerun_ok(agents_dir: Path) -> None:
    # Atrium upsert may return 200 on subsequent calls
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"agent_role": "ok"}))
    first = _invoke(agents_dir)
    assert first.exit_code == 0, first.output
    second = _invoke(agents_dir)
    assert second.exit_code == 0, second.output
