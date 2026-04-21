"""Tests for daemon reconcile_orphans — UUID IDs, /api/ prefix."""

from __future__ import annotations

import json
import signal
import uuid
from unittest.mock import patch

import httpx
import respx

from nexus.daemon import reconcile_orphans

_BASE = "http://localhost:8100"
_ID1 = str(uuid.uuid4())
_ID2 = str(uuid.uuid4())
_ID3 = str(uuid.uuid4())


def _item(item_id: str, pid: int | None = 99999) -> dict:
    return {
        "id": item_id,
        "type": "code-search",
        "agent_role": "code-agent",
        "priority": "P2",
        "status": "running",
        "context": {"pid": pid} if pid is not None else {},
        "result": None,
        "created_at": "2026-04-20T10:00:00Z",
        "started_at": "2026-04-20T10:01:00Z",
        "completed_at": None,
        "token_cost": 0,
    }


@respx.mock
async def test_dead_pid_patches_to_failed():
    respx.get(f"{_BASE}/api/work_items").mock(
        return_value=httpx.Response(200, json=[_item(_ID1, pid=99999)])
    )
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ID1}").mock(
        return_value=httpx.Response(200, json={})
    )

    with patch("os.kill", side_effect=ProcessLookupError):
        async with httpx.AsyncClient(base_url=_BASE) as client:
            await reconcile_orphans(client)

    assert patch_route.called
    body = json.loads(patch_route.calls[0].request.content)
    assert body["status"] == "failed"
    assert "Orphaned" in body["result"]["error"]


@respx.mock
async def test_no_running_items_is_noop():
    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[]))
    async with httpx.AsyncClient(base_url=_BASE) as client:
        await reconcile_orphans(client)


@respx.mock
async def test_item_without_pid_marked_failed():
    item = _item(_ID2, pid=None)
    respx.get(f"{_BASE}/api/work_items").mock(return_value=httpx.Response(200, json=[item]))
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ID2}").mock(
        return_value=httpx.Response(200, json={})
    )

    async with httpx.AsyncClient(base_url=_BASE) as client:
        await reconcile_orphans(client)

    assert patch_route.called


@respx.mock
async def test_live_pid_is_sigtermd_and_marked_failed():
    respx.get(f"{_BASE}/api/work_items").mock(
        return_value=httpx.Response(200, json=[_item(_ID3, pid=77777)])
    )
    patch_route = respx.patch(f"{_BASE}/api/work_items/{_ID3}").mock(
        return_value=httpx.Response(200, json={})
    )

    kill_calls: list[tuple[int, int]] = []
    liveness_count = 0

    def fake_kill(pid: int, sig: int) -> None:
        nonlocal liveness_count
        kill_calls.append((pid, sig))
        if sig == 0:
            liveness_count += 1
            if liveness_count > 1:
                raise ProcessLookupError  # dead after SIGTERM

    with (
        patch("os.kill", side_effect=fake_kill),
        patch("os.getpgid", return_value=77777),
        patch("asyncio.sleep"),
    ):
        async with httpx.AsyncClient(base_url=_BASE) as client:
            await reconcile_orphans(client)

    assert patch_route.called
    sigterms = [s for _, s in kill_calls if s == signal.SIGTERM]
    assert sigterms


@respx.mock
async def test_multiple_orphans_all_patched():
    id_a, id_b = str(uuid.uuid4()), str(uuid.uuid4())
    respx.get(f"{_BASE}/api/work_items").mock(
        return_value=httpx.Response(200, json=[_item(id_a, 11111), _item(id_b, 22222)])
    )
    pa = respx.patch(f"{_BASE}/api/work_items/{id_a}").mock(
        return_value=httpx.Response(200, json={})
    )
    pb = respx.patch(f"{_BASE}/api/work_items/{id_b}").mock(
        return_value=httpx.Response(200, json={})
    )

    with patch("os.kill", side_effect=ProcessLookupError):
        async with httpx.AsyncClient(base_url=_BASE) as client:
            await reconcile_orphans(client)

    assert pa.called and pb.called


@respx.mock
async def test_atrium_error_does_not_raise():
    respx.get(f"{_BASE}/api/work_items").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient(base_url=_BASE) as client:
        await reconcile_orphans(client)  # must not raise
