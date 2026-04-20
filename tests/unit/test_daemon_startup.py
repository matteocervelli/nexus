"""Tests for daemon on_startup / reconcile_orphans — TDD red phase."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from nexus.daemon import reconcile_orphans


def running_work_item(item_id: int, pid: int) -> dict:
    return {
        "id": item_id,
        "type": "code-search",
        "agent_role": "code-agent",
        "priority": "P2",
        "status": "running",
        "context": {"pid": pid},
        "result": None,
        "created_at": "2026-04-20T10:00:00Z",
        "started_at": "2026-04-20T10:01:00Z",
        "completed_at": None,
        "token_cost": 0,
    }


class TestReconcileOrphansDeadPid:
    @respx.mock
    async def test_dead_pid_patches_to_failed(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[running_work_item(1, 99999)])
        )
        patch_route = respx.patch("http://localhost:8100/work_items/1").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        with patch("os.kill", side_effect=ProcessLookupError):
            async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
                await reconcile_orphans(client)

        assert patch_route.called
        body = json.loads(patch_route.calls[0].request.content)
        assert body["status"] == "failed"
        assert "Orphaned" in body["error_message"]

    @respx.mock
    async def test_dead_pid_writes_audit_log(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[running_work_item(2, 88888)])
        )
        respx.patch("http://localhost:8100/work_items/2").mock(
            return_value=httpx.Response(200, json={})
        )
        audit_route = respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        with patch("os.kill", side_effect=ProcessLookupError):
            async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
                await reconcile_orphans(client)

        assert audit_route.called
        body = json.loads(audit_route.calls[0].request.content)
        assert body["work_item_id"] == 2


class TestReconcileOrphansLivePid:
    @respx.mock
    async def test_live_pid_is_killed_and_marked_failed(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[running_work_item(3, 77777)])
        )
        patch_route = respx.patch("http://localhost:8100/work_items/3").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        kill_calls: list[tuple] = []

        def fake_kill(pid: int, sig: int) -> None:
            kill_calls.append((pid, sig))

        with patch("os.kill", side_effect=fake_kill), patch("os.getpgid", return_value=77777), patch("asyncio.sleep"):
            async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
                await reconcile_orphans(client)

        assert patch_route.called
        body = json.loads(patch_route.calls[0].request.content)
        assert body["status"] == "failed"
        # At least one SIGTERM was sent
        import signal
        sigterms = [s for _, s in kill_calls if s == signal.SIGTERM]
        assert sigterms, "Expected SIGTERM to be sent to live process"

    @respx.mock
    async def test_live_pid_writes_audit_log(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[running_work_item(4, 66666)])
        )
        respx.patch("http://localhost:8100/work_items/4").mock(
            return_value=httpx.Response(200, json={})
        )
        audit_route = respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        with patch("os.kill"), patch("os.getpgid", return_value=66666), patch("asyncio.sleep"):
            async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
                await reconcile_orphans(client)

        assert audit_route.called


class TestReconcileOrphansEdgeCases:
    @respx.mock
    async def test_no_running_items_is_noop(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[])
        )

        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            await reconcile_orphans(client)
        # No exceptions — empty list handled gracefully

    @respx.mock
    async def test_item_without_pid_is_marked_failed(self):
        """work_item.context has no 'pid' key — treat as orphan with unknown PID."""
        item = running_work_item(5, 0)
        item["context"] = {}  # no pid
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(200, json=[item])
        )
        patch_route = respx.patch("http://localhost:8100/work_items/5").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
            await reconcile_orphans(client)

        assert patch_route.called

    @respx.mock
    async def test_multiple_orphans_all_handled(self):
        respx.get("http://localhost:8100/work_items").mock(
            return_value=httpx.Response(
                200,
                json=[running_work_item(6, 11111), running_work_item(7, 22222)],
            )
        )
        patch6 = respx.patch("http://localhost:8100/work_items/6").mock(
            return_value=httpx.Response(200, json={})
        )
        patch7 = respx.patch("http://localhost:8100/work_items/7").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post("http://localhost:8100/agent_results").mock(
            return_value=httpx.Response(201, json={})
        )

        with patch("os.kill", side_effect=ProcessLookupError):
            async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
                await reconcile_orphans(client)

        assert patch6.called
        assert patch7.called
