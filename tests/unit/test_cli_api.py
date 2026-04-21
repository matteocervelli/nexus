"""Tests for the `nexus api` CLI subcommand."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from nexus.cli import cli


def test_api_command_calls_uvicorn_run():
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(cli, ["api", "--port", "8200"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("port") == 8200 or mock_run.call_args[0][1] == 8200


def test_api_command_default_port():
    runner = CliRunner()
    with patch("uvicorn.run") as mock_run:
        runner.invoke(cli, ["api"])
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    port = (
        call_args[1].get("port") or call_args[0][2]
        if len(call_args[0]) > 2
        else call_args[1].get("port")
    )
    assert port == 8200
