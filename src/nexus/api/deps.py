import httpx
from fastapi import Request

from nexus.events import EventBus


def get_atrium_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient = request.app.state.atrium_client
    return client


def get_event_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus
