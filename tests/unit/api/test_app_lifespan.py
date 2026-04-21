"""Tests for create_app lifespan and client ownership."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_owns_client_false_when_external_client_injected():
    from nexus.api import create_app

    external = httpx.AsyncClient(base_url="http://atrium-test")
    app = create_app(atrium_url="http://atrium-test", atrium_client=external)

    with respx.mock(base_url="http://atrium-test") as mock:
        mock.get("/api/work_items").respond(200, json=[])
        mock.get("/api/agent_registry").respond(200, json=[])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/nexus/api/status")
            assert app.state.owns_client is False
            assert app.state.atrium_client is external

    # App did not close the external client
    assert not external.is_closed
    await external.aclose()


@pytest.mark.asyncio
async def test_owns_client_true_when_no_external_client():
    """App creates and owns its own client when none injected; lifespan verified via state."""
    from nexus.api import create_app

    # Inject a pre-built client to avoid hitting real Atrium, but create app without it
    # to test the owns_client=True path
    app = create_app(atrium_url="http://atrium-test")

    # Manually trigger lifespan to verify owns_client is set correctly
    lifespan_cm = app.router.lifespan_context(app)
    async with lifespan_cm:
        assert app.state.owns_client is True
        owned_client = app.state.atrium_client
        assert isinstance(owned_client, httpx.AsyncClient)

    # After lifespan exits the owned client should be closed
    assert owned_client.is_closed
