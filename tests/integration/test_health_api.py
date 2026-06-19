import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_health_endpoint(client: AsyncClient):
    client.headers.pop("X-API-Key", None)
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "checks" in data


@pytest.mark.integration
async def test_info_endpoint(client: AsyncClient):
    client.headers.pop("X-API-Key", None)
    resp = await client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "payment-gateway-core"
    assert data["version"] == "1.0.0"
