"""TDD tests for the Nexus dashboard API endpoints."""

from __future__ import annotations

import pytest
import respx
from httpx import ASGITransport, AsyncClient

WORKFLOW_1 = {
    "id": "wf-001",
    "name": "Test Workflow",
    "status": "running",
    "created_at": "2026-04-21T10:00:00",
    "started_at": "2026-04-21T10:01:00",
    "completed_at": None,
}

WORKFLOW_DETAIL = {
    **WORKFLOW_1,
    "steps": [
        {
            "id": "step-001",
            "agent_role": "code-agent",
            "status": "done",
            "step_index": 0,
            "depends_on": [],
            "started_at": "2026-04-21T10:01:00",
            "completed_at": "2026-04-21T10:02:00",
        }
    ],
    "dag": {"step-001": []},
    "updated_at": "2026-04-21T10:02:00",
}

AGENT_1 = {
    "agent_role": "code-agent",
    "execution_backend": "claude-code-cli",
    "model": "claude-sonnet-4-6",
    "monthly_token_budget": 100000,
}

LEDGER_1 = {"tokens_consumed": 50000}


# ---------------------------------------------------------------------------
# Task 10: GET /nexus/api/workflows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workflows_happy_path(nexus_api_client, nexus_api_app):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/workflows").respond(200, json=[WORKFLOW_1])
        resp = await nexus_api_client.get("/nexus/api/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "wf-001"


@pytest.mark.asyncio
async def test_list_workflows_empty(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/workflows").respond(200, json=[])
        resp = await nexus_api_client.get("/nexus/api/workflows")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_workflows_forwards_query_params(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        route = mock.get("/api/workflows").respond(200, json=[WORKFLOW_1])
        resp = await nexus_api_client.get(
            "/nexus/api/workflows", params={"status": "running", "limit": 10, "offset": 0}
        )
    assert resp.status_code == 200
    called_url = str(route.calls[0].request.url)
    assert "status=running" in called_url
    assert "limit=10" in called_url
    assert "offset=0" in called_url


@pytest.mark.asyncio
async def test_list_workflows_upstream_5xx_returns_502(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/workflows").respond(500)
        resp = await nexus_api_client.get("/nexus/api/workflows")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_list_workflows_cors_preflight(nexus_api_app):
    async with AsyncClient(
        transport=ASGITransport(app=nexus_api_app), base_url="http://test"
    ) as client:
        resp = await client.options(
            "/nexus/api/workflows",
            headers={
                "Origin": "http://localhost:5273",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# Task 11: GET /nexus/api/workflows/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/workflows/wf-001").respond(200, json=WORKFLOW_DETAIL)
        resp = await nexus_api_client.get("/nexus/api/workflows/wf-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "wf-001"
    assert len(data["steps"]) == 1


@pytest.mark.asyncio
async def test_get_workflow_404(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/workflows/missing").respond(404)
        resp = await nexus_api_client.get("/nexus/api/workflows/missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 12: PATCH /nexus/api/workflows/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_workflow_happy_path(nexus_api_client):
    cancelled = {**WORKFLOW_1, "status": "cancelled"}
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.patch("/api/workflows/wf-001").respond(200, json=cancelled)
        resp = await nexus_api_client.patch(
            "/nexus/api/workflows/wf-001", json={"action": "cancel"}
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_workflow_404(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.patch("/api/workflows/missing").respond(404)
        resp = await nexus_api_client.patch(
            "/nexus/api/workflows/missing", json={"action": "cancel"}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_workflow_invalid_body_422(nexus_api_client):
    resp = await nexus_api_client.patch("/nexus/api/workflows/wf-001", json={"action": "delete"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Task 13: GET /nexus/api/agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/agent_registry").respond(200, json=[AGENT_1])
        mock.get("/api/work_items").respond(200, json=[])
        mock.get("/api/budget_ledger").respond(200, json=LEDGER_1)
        resp = await nexus_api_client.get("/nexus/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_role"] == "code-agent"
    assert data[0]["tokens_used_this_month"] == 50000


@pytest.mark.asyncio
async def test_list_agents_budget_404_returns_zero(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/agent_registry").respond(200, json=[AGENT_1])
        mock.get("/api/work_items").respond(200, json=[])
        mock.get("/api/budget_ledger").respond(404)
        resp = await nexus_api_client.get("/nexus/api/agents")
    assert resp.status_code == 200
    assert resp.json()[0]["tokens_used_this_month"] == 0


# ---------------------------------------------------------------------------
# Task 14: GET /nexus/api/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_happy_path(nexus_api_client):
    running = [{"agent_role": "code-agent", "status": "running"}]
    pending = [{"agent_role": "code-agent", "status": "pending"}] * 3
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items", params={"status": "running"}).respond(200, json=running)
        mock.get("/api/work_items", params={"status": "pending"}).respond(200, json=pending)
        mock.get("/api/agent_registry").respond(200, json=[AGENT_1])
        mock.get("/api/budget_ledger").respond(200, json={"tokens_consumed": 80001})
        resp = await nexus_api_client.get("/nexus/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running_count"] == 1
    assert data["queue_depth"] == 3
    assert len(data["budget_alerts"]) == 1
    alert = data["budget_alerts"][0]
    assert alert["agent_role"] == "code-agent"
    assert alert["percent"] >= 80.0


@pytest.mark.asyncio
async def test_get_status_budget_alerts_only_above_80(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items", params={"status": "running"}).respond(200, json=[])
        mock.get("/api/work_items", params={"status": "pending"}).respond(200, json=[])
        mock.get("/api/agent_registry").respond(200, json=[AGENT_1])
        # 79% usage — should NOT trigger alert
        mock.get("/api/budget_ledger").respond(200, json={"tokens_consumed": 79000})
        resp = await nexus_api_client.get("/nexus/api/status")
    assert resp.status_code == 200
    assert resp.json()["budget_alerts"] == []


# ---------------------------------------------------------------------------
# GET /nexus/api/work_items
# ---------------------------------------------------------------------------

WORK_ITEM_1 = {
    "id": "wi-001",
    "type": "scan",
    "agent_role": "code-agent",
    "priority": "P2",
    "status": "running",
    "context": {"repo": "nexus"},
    "result": None,
    "token_cost": 0,
    "created_at": "2026-04-21T10:00:00Z",
    "updated_at": None,
    "started_at": "2026-04-21T10:01:00Z",
    "completed_at": None,
}


@pytest.mark.asyncio
async def test_list_work_items_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items").respond(200, json=[WORK_ITEM_1])
        resp = await nexus_api_client.get("/nexus/api/work_items")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "wi-001"
    assert data[0]["agent_role"] == "code-agent"


@pytest.mark.asyncio
async def test_list_work_items_empty(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items").respond(200, json=[])
        resp = await nexus_api_client.get("/nexus/api/work_items")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_work_items_forwards_filters(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        route = mock.get("/api/work_items").respond(200, json=[WORK_ITEM_1])
        resp = await nexus_api_client.get(
            "/nexus/api/work_items",
            params={"status": "running", "agent_role": "code-agent", "limit": 20},
        )
    assert resp.status_code == 200
    called_url = str(route.calls[0].request.url)
    assert "status=running" in called_url
    assert "agent_role=code-agent" in called_url
    assert "limit=20" in called_url


@pytest.mark.asyncio
async def test_list_work_items_upstream_5xx(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items").respond(500)
        resp = await nexus_api_client.get("/nexus/api/work_items")
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /nexus/api/runs  +  GET /nexus/api/runs/{id}  +  GET /nexus/api/runs/{id}/events
# ---------------------------------------------------------------------------

RUN_1 = {
    "id": "run-001",
    "work_item_id": "wi-001",
    "workflow_step_id": None,
    "agent_role": "code-agent",
    "execution_backend": "anthropic-sdk",
    "model": "claude-sonnet-4-6",
    "status": "succeeded",
    "started_at": "2026-04-21T10:01:00Z",
    "finished_at": "2026-04-21T10:05:00Z",
    "tokens_total": 1500,
    "cost_usd": 0.003,
    "created_at": "2026-04-21T10:01:00Z",
    "updated_at": "2026-04-21T10:05:00Z",
}

RUN_DETAIL_1 = {
    **RUN_1,
    "external_run_id": None,
    "session_kind": None,
    "session_id_before": None,
    "session_id_after": None,
    "session_metadata": None,
    "tokens_input": 1000,
    "tokens_output": 500,
    "cost_source": "sdk",
    "stdout_excerpt": "Task done.",
    "stderr_excerpt": None,
    "result_payload": {"status": "ok"},
    "error_code": None,
    "error_message": None,
}

RUN_EVENT_1 = {
    "id": "ev-001",
    "run_id": "run-001",
    "event_index": 0,
    "event_type": "tool_call",
    "tool_name": "Bash",
    "payload": {"command": "ls /"},
    "occurred_at": "2026-04-21T10:01:01Z",
    "created_at": "2026-04-21T10:01:01Z",
}


@pytest.mark.asyncio
async def test_list_runs_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log").respond(200, json=[RUN_1])
        resp = await nexus_api_client.get("/nexus/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "run-001"
    assert data[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_list_runs_forwards_filters(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        route = mock.get("/api/run_log").respond(200, json=[RUN_1])
        resp = await nexus_api_client.get(
            "/nexus/api/runs",
            params={"agent_role": "code-agent", "status": "succeeded", "limit": 10},
        )
    assert resp.status_code == 200
    called_url = str(route.calls[0].request.url)
    assert "agent_role=code-agent" in called_url
    assert "status=succeeded" in called_url
    assert "limit=10" in called_url


@pytest.mark.asyncio
async def test_list_runs_upstream_5xx(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log").respond(500)
        resp = await nexus_api_client.get("/nexus/api/runs")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_get_run_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/run-001").respond(200, json=RUN_DETAIL_1)
        resp = await nexus_api_client.get("/nexus/api/runs/run-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "run-001"
    assert data["stdout_excerpt"] == "Task done."
    assert data["tokens_input"] == 1000


@pytest.mark.asyncio
async def test_get_run_not_found(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/missing").respond(404)
        resp = await nexus_api_client.get("/nexus/api/runs/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_upstream_5xx(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/run-001").respond(500)
        resp = await nexus_api_client.get("/nexus/api/runs/run-001")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_list_run_events_happy_path(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/run-001/events").respond(200, json=[RUN_EVENT_1])
        resp = await nexus_api_client.get("/nexus/api/runs/run-001/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_type"] == "tool_call"
    assert data[0]["event_index"] == 0


@pytest.mark.asyncio
async def test_list_run_events_run_not_found(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/missing/events").respond(404)
        resp = await nexus_api_client.get("/nexus/api/runs/missing/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_run_events_upstream_5xx(nexus_api_client):
    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/run_log/run-001/events").respond(500)
        resp = await nexus_api_client.get("/nexus/api/runs/run-001/events")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_list_work_items_multi_status_filter(nexus_api_client):
    """Multi-status filter sends repeated query params, not a single scalar."""
    with respx.mock(base_url="http://atrium-test") as mock:
        route = mock.get("/api/work_items").respond(200, json=[WORK_ITEM_1])
        resp = await nexus_api_client.get(
            "/nexus/api/work_items",
            params=[("status", "running"), ("status", "done"), ("status", "failed")],
        )
    assert resp.status_code == 200
    called_url = str(route.calls[0].request.url)
    assert called_url.count("status=") == 3


@pytest.mark.asyncio
async def test_list_work_items_transport_error(nexus_api_client):
    import httpx as _httpx

    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items").mock(side_effect=_httpx.ConnectError("refused"))
        resp = await nexus_api_client.get("/nexus/api/work_items")
    assert resp.status_code == 502
