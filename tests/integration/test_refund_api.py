import uuid

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from paygateway.providers.base import ProviderRefund, ProviderWebhookEvent


async def _create_succeeded_payment(client: AsyncClient, mock_provider: AsyncMock, amount: int = 5000) -> str:
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": amount, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert create_resp.status_code == 201
    payment_id = create_resp.json()["id"]

    event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded",
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = event
    await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    return payment_id


@pytest.mark.integration
async def test_create_refund_success(client: AsyncClient, mock_provider: AsyncMock):
    payment_id = await _create_succeeded_payment(client, mock_provider)

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_test_456",
        payment_provider_id="pi_test_123",
        amount=5000,
        currency="USD",
        status="pending",
    )

    refund_resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refund_resp.status_code == 201
    data = refund_resp.json()
    assert data["amount"] == 5000
    assert data["status"] == "pending"
    assert data["payment_id"] == payment_id


@pytest.mark.integration
async def test_create_partial_refund(client: AsyncClient, mock_provider: AsyncMock):
    payment_id = await _create_succeeded_payment(client, mock_provider)

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_partial",
        payment_provider_id="pi_test_123",
        amount=3000,
        currency="USD",
        status="pending",
    )

    refund_resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 3000, "reason": "requested_by_customer"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refund_resp.status_code == 201
    assert refund_resp.json()["amount"] == 3000


@pytest.mark.integration
async def test_create_refund_payment_not_found(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.integration
async def test_create_refund_not_refundable(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "PAYMENT_NOT_REFUNDABLE"


@pytest.mark.integration
async def test_create_refund_missing_idempotency_key(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/payments/{payment_id}/refund", json={})
    assert resp.status_code == 422


@pytest.mark.integration
async def test_list_refunds_empty(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/payments/{payment_id}/refunds")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] == 0
    assert data["data"] == []


@pytest.mark.integration
async def test_get_refund_not_found(client: AsyncClient):
    resp = await client.get(f"/api/v1/refunds/{uuid.uuid4()}")
    assert resp.status_code == 404
