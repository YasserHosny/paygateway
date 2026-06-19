import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_same_idempotency_key_same_body_returns_same_response(client: AsyncClient):
    key = str(uuid.uuid4())
    body = {"amount": 5000, "currency": "usd"}

    resp1 = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": key})
    resp2 = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": key})

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.integration
async def test_missing_idempotency_key_returns_422(client: AsyncClient):
    resp = await client.post("/api/v1/payments", json={"amount": 5000, "currency": "usd"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["error"]["code"] == "IDEMPOTENCY_KEY_MISSING"


@pytest.mark.integration
async def test_idempotency_key_isolation_between_payments(client: AsyncClient):
    key1 = str(uuid.uuid4())
    key2 = str(uuid.uuid4())

    resp1 = await client.post(
        "/api/v1/payments",
        json={"amount": 1000, "currency": "usd"},
        headers={"Idempotency-Key": key1},
    )
    resp2 = await client.post(
        "/api/v1/payments",
        json={"amount": 2000, "currency": "usd"},
        headers={"Idempotency-Key": key2},
    )

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] != resp2.json()["id"]
