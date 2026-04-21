"""FastAPI application factory for the Nexus dashboard API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus.api.dashboard import router as dashboard_router


def create_app(
    atrium_url: str | None = None,
    cors_origins: list[str] | None = None,
    atrium_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    resolved_url = atrium_url or os.environ.get("ATRIUM_URL", "http://localhost:8100")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        if not app.state.owns_client:
            yield
            return
        client = httpx.AsyncClient(
            base_url=resolved_url,
            timeout=httpx.Timeout(connect=5, read=30, write=10, pool=None),
        )
        app.state.atrium_client = client
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="Nexus Dashboard API", lifespan=lifespan)
    app.state.atrium_url = resolved_url

    if atrium_client is not None:
        app.state.atrium_client = atrium_client
        app.state.owns_client = False
    else:
        app.state.owns_client = True

    env_origins = os.environ.get("NEXUS_CORS_ORIGINS", "")
    raw_origins_str: str = env_origins if cors_origins is None else ",".join(cors_origins)
    if raw_origins_str:
        origins = [o.strip() for o in raw_origins_str.split(",") if o.strip()]
    else:
        origins = ["http://localhost:5273"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(dashboard_router)
    return app
