"""Tests for daemon + API server integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_daemon_starts_api_server_when_serve_api_true():
    """Daemon creates uvicorn server task when serve_api=True."""
    from nexus.daemon import NexusDaemon

    daemon = NexusDaemon(atrium_url="http://localhost:8100", serve_api=True, api_port=8200)

    mock_server = MagicMock()
    mock_server.serve = AsyncMock(return_value=None)
    mock_server.install_signal_handlers = lambda: None
    mock_server.started = True  # signal immediate bind success to skip the wait loop

    with (
        patch("nexus.daemon.reconcile_orphans", new=AsyncMock()),
        patch("nexus.daemon.Scheduler") as mock_sched_cls,
        patch("nexus.daemon.BudgetChecker"),
        patch("nexus.daemon.uvicorn.Server", return_value=mock_server),
        patch("nexus.daemon.uvicorn.Config"),
    ):
        mock_sched = MagicMock()
        mock_sched.tick = AsyncMock(return_value=None)
        mock_sched_cls.return_value = mock_sched

        task = asyncio.create_task(daemon.start())
        await asyncio.sleep(0.05)
        await daemon.stop()
        await asyncio.wait_for(task, timeout=2)

    mock_server.serve.assert_called_once()


@pytest.mark.asyncio
async def test_daemon_skips_api_server_when_serve_api_false():
    """Daemon does not create uvicorn server task when serve_api=False."""
    from nexus.daemon import NexusDaemon

    daemon = NexusDaemon(atrium_url="http://localhost:8100", serve_api=False)

    with (
        patch("nexus.daemon.reconcile_orphans", new=AsyncMock()),
        patch("nexus.daemon.Scheduler") as mock_sched_cls,
        patch("nexus.daemon.BudgetChecker"),
        patch("nexus.daemon.uvicorn.Server") as mock_server_cls,
    ):
        mock_sched = MagicMock()
        mock_sched.tick = AsyncMock(return_value=None)
        mock_sched_cls.return_value = mock_sched

        task = asyncio.create_task(daemon.start())
        await asyncio.sleep(0.05)
        await daemon.stop()
        await asyncio.wait_for(task, timeout=2)

    mock_server_cls.assert_not_called()
