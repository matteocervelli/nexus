"""Nexus daemon — startup lifecycle and heartbeat loop.

on_startup() runs synchronously before the heartbeat loop begins.
It calls reconcile_orphans() to flip stale running records to failed.
"""

from __future__ import annotations

import asyncio
import os
import signal
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_SIGKILL_WAIT = 5


async def reconcile_orphans(atrium_client: httpx.AsyncClient) -> None:
    """Flip all running work_items to failed, killing live processes.

    Runs at daemon startup before the heartbeat loop. Handles two cases:
    - PID dead: mark failed, write audit entry.
    - PID alive: SIGTERM → wait → SIGKILL, then mark failed, write audit.
    - No PID in context: mark failed (unknown orphan), write audit.
    """
    log = logger.bind(phase="startup.reconcile_orphans")

    try:
        resp = await atrium_client.get(
            "/work_items", params={"status": "running"}
        )
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
        item_id: int = item["id"]
        pid: int | None = item.get("context", {}).get("pid")
        await _reconcile_one(atrium_client, item_id=item_id, pid=pid)


async def _reconcile_one(
    client: httpx.AsyncClient,
    item_id: int,
    pid: int | None,
) -> None:
    log = logger.bind(work_item_id=item_id, pid=pid)

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
    await _write_audit(client, item_id=item_id, reason=reason)


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
    item_id: int,
    reason: str,
    log: Any,
) -> None:
    try:
        await client.patch(
            f"/work_items/{item_id}",
            json={"status": "failed", "error_message": reason},
        )
    except Exception as exc:
        log.error("reconcile.patch_error", error=str(exc))


async def _write_audit(
    client: httpx.AsyncClient,
    item_id: int,
    reason: str,
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        await client.post(
            "/agent_results",
            json={
                "work_item_id": item_id,
                "event": "orphan_reconciled",
                "detail": reason,
                "recorded_at": now,
            },
        )
    except Exception as exc:
        logger.error("reconcile.audit_error", work_item_id=item_id, error=str(exc))


async def on_startup(atrium_client: httpx.AsyncClient) -> None:
    """Run all startup tasks before the heartbeat loop begins."""
    await reconcile_orphans(atrium_client)
