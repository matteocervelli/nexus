import httpx
from fastapi import Request


def get_atrium_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient = request.app.state.atrium_client
    return client
