import pytest
from httpx import AsyncClient
from app.main import app

# Why AsyncClient? FastAPI is ASGI (async). This lets you call your app in-memory without a real server.
@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
