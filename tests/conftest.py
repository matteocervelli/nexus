"""Shared test fixtures for the Nexus test suite."""

from __future__ import annotations

import pathlib
from collections.abc import AsyncGenerator

import httpx
import pytest
import respx


@pytest.fixture
def atrium_mock() -> respx.MockRouter:
    """Mock Atrium HTTP API — use as a context manager or let respx handle cleanup."""
    with respx.mock(base_url="http://localhost:8100") as router:
        yield router


@pytest.fixture
async def atrium_client(atrium_mock: respx.MockRouter) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Pre-wired async httpx client pointing at the mocked Atrium."""
    async with httpx.AsyncClient(base_url="http://localhost:8100") as client:
        yield client


@pytest.fixture
def tmp_profile_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal agent profile directory with a CLAUDE.md stub."""
    profile = tmp_path / "agent-profile"
    profile.mkdir()
    (profile / "CLAUDE.md").write_text(
        "# Test Agent\nYou are a test agent. Reply concisely.\n"
    )
    return profile
