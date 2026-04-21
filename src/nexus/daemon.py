"""Nexus daemon — startup lifecycle and heartbeat loop.

NexusDaemon wires together: reconcile_orphans (startup), scheduler (heartbeat).
on_startup() runs before the heartbeat loop so no stale running items pollute
the first tick.

Heartbeat interval and Atrium URL are controlled by env vars:
  ATRIUM_URL   (default http://localhost:8100)
  NEXUS_HEARTBEAT_INTERVAL_SECONDS (default 30)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import uuid
from typing import Any

import httpx
import structlog
import uvicorn

from nexus.budget import BudgetChecker
from nexus.events import EventBus
from nexus.scheduler import Scheduler

logger = structlog.get_logger(__name__)

_SIGKILL_WAIT = 5
_DEFAULT_ATRIUM_URL = "http://localhost:8100"
_DEFAULT_HEARTBEAT_INTERVAL = 30


# ---------------------------------------------------------------------------
# Reconciliation — runs at daemon startup
# ---------------------------------------------------------------------------


async def reconcile_orphans(atrium_client: httpx.AsyncClient) -> None:
    """Flip all running work_items to failed, killing live processes.

    Runs at daemon startup before the heartbeat loop. Handles three cases:
    - PID dead: mark failed, write audit entry.
    - PID alive: SIGTERM → wait → SIGKILL, then mark failed, write audit.
    - No PID in context: mark failed (unknown orphan), write audit.
    """
    log = logger.bind(phase="startup.reconcile_orphans")

    try:
        resp = await atrium_client.get("/api/work_items", params={"status": "running"})
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json()
    except Exception as exc:
        log.error("reconcile.fetch_error", error=str(exc))
        return

    if not items:
        log.info("reconcile.no_orphans")
        return

    log.info("reconcile.found_orphans", count=len(items))

    for item in items:
        item_id = uuid.UUID(str(item["id"]))
        pid: int | None = item.get("context", {}).get("pid")
        await _reconcile_one(atrium_client, item_id=item_id, pid=pid)


async def _reconcile_one(
    client: httpx.AsyncClient,
    item_id: uuid.UUID,
    pid: int | None,
) -> None:
    log = logger.bind(work_item_id=str(item_id), pid=pid)

    if pid is None:
        log.warning("reconcile.no_pid")
        reason = "Orphaned on daemon restart (no PID recorded)"
    else:
        alive = _pid_alive(pid)
        if alive:
            log.warning("reconcile.killing_live_process")
            await _kill_process(pid, log)
            reason = "Orphaned on daemon restart (process killed)"
        else:
            log.info("reconcile.dead_pid")
            reason = "Orphaned on daemon restart"

    await _mark_failed(client, item_id=item_id, reason=reason, log=log)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


async def _kill_process(pid: int, log: Any) -> None:
    try:
        pgid = os.getpgid(pid)
        os.kill(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    await asyncio.sleep(_SIGKILL_WAIT)

    if _pid_alive(pid):
        try:
            pgid = os.getpgid(pid)
            os.kill(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def _mark_failed(
    client: httpx.AsyncClient,
    item_id: uuid.UUID,
    reason: str,
    log: Any,
) -> None:
    try:
        await client.patch(
            f"/api/work_items/{item_id}",
            json={"status": "failed", "result": {"error": reason}},
        )
    except Exception as exc:
        log.error("reconcile.patch_error", error=str(exc))


# ---------------------------------------------------------------------------
# Daemon lifecycle — heartbeat loop added in Phase C #9
# ---------------------------------------------------------------------------


class NexusDaemon:
    """Nexus orchestration daemon.

    Startup sequence:
      1. reconcile_orphans() — clear stale running items
      2. heartbeat_loop() — poll and dispatch until stop()

    Usage:
      daemon = NexusDaemon()
      await daemon.start()   # blocks until stop() or SIGTERM
    """

    def __init__(
        self,
        atrium_url: str | None = None,
        heartbeat_interval: int | None = None,
        serve_api: bool = True,
        api_port: int = 8200,
    ) -> None:
        self._atrium_url = atrium_url or os.environ.get("ATRIUM_URL", _DEFAULT_ATRIUM_URL)
        self._heartbeat_interval = heartbeat_interval or int(
            os.environ.get("NEXUS_HEARTBEAT_INTERVAL_SECONDS", _DEFAULT_HEARTBEAT_INTERVAL)
        )
        self._stop_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None
        self._scheduler: Scheduler | None = None
        self._serve_api = serve_api
        self._api_port = api_port

    async def start(self) -> None:
        """Start the daemon. Blocks until stop() is called or SIGTERM received."""
        log = logger.bind(atrium_url=self._atrium_url)
        log.info("daemon.starting")

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self._on_sigterm)
        loop.add_signal_handler(signal.SIGINT, self._on_sigterm)

        api_task: asyncio.Task[None] | None = None
        api_server: uvicorn.Server | None = None

        async with httpx.AsyncClient(
            base_url=self._atrium_url,
            timeout=httpx.Timeout(connect=5, read=30, write=10, pool=None),
        ) as client:
            self._client = client
            event_bus = EventBus()
            self._scheduler = Scheduler(client, BudgetChecker(client, event_bus), event_bus)
            await reconcile_orphans(client)

            if self._serve_api:
                from nexus.api import create_app

                app = create_app(atrium_client=client, event_bus=event_bus)
                config = uvicorn.Config(app, host="127.0.0.1", port=self._api_port, log_config=None)
                api_server = uvicorn.Server(config)
                api_server.install_signal_handlers = lambda: None  # type: ignore[attr-defined]
                api_task = asyncio.create_task(api_server.serve(), name="nexus-api")
                # Wait until uvicorn binds the socket before logging startup_complete.
                # started is set by uvicorn after successful socket bind.
                for _ in range(50):
                    if api_server.started:
                        break
                    if api_task.done():
                        raise RuntimeError(f"API server failed to start on port {self._api_port}")
                    await asyncio.sleep(0.1)
                else:
                    api_server.should_exit = True
                    raise RuntimeError(
                        f"API server did not start within 5 s on port {self._api_port}"
                    )

            log.info("daemon.startup_complete")
            try:
                await self._heartbeat_loop(client)
            finally:
                if api_server is not None and api_task is not None:
                    api_server.should_exit = True
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(api_task, timeout=5)

        log.info("daemon.stopped")

    async def stop(self) -> None:
        self._stop_event.set()

    def _on_sigterm(self) -> None:
        logger.info("daemon.sigterm_received")
        self._stop_event.set()

    async def _heartbeat_loop(self, client: httpx.AsyncClient) -> None:
        """Poll Atrium and dispatch work items. Placeholder — filled in Phase C #9."""
        log = logger.bind(interval=self._heartbeat_interval)
        log.info("daemon.heartbeat_loop_started")

        while not self._stop_event.is_set():
            try:
                await self._tick(client)
            except Exception as exc:
                log.error("daemon.tick_error", error=str(exc))

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=self._heartbeat_interval,
                )

    async def _tick(self, client: httpx.AsyncClient) -> None:
        if self._scheduler is None:
            return
        await self._scheduler.tick()
