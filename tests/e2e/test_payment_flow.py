"""
E2E tests for the complete payment lifecycle.
These tests simulate the full flow: create → confirm → webhook → status check.
Provider calls are mocked; the full service + route + DB stack is exercised.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from paygateway.providers.base import ProviderPaymentIntent, ProviderWebhookEvent


@pytest.mark.e2e
async def test_full_payment_lifecycle(client: AsyncClient, mock_provider: AsyncMock):
    idem_key = str(uuid.uuid4())
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd", "description": "E2E test"},
        headers={"Idempotency-Key": idem_key},
    )
    assert create_resp.status_code == 201
    payment = create_resp.json()
    payment_id = payment["id"]
    assert payment["status"] == "pending"
    assert payment["client_secret"] is not None

    mock_provider.confirm_payment_intent.return_value = ProviderPaymentIntent(
        provider_id="pi_test_123",
        status="succeeded",
        amount=5000,
        currency="USD",
    )
    confirm_resp = await client.post(
        f"/api/v1/payments/{payment_id}/confirm",
        json={"payment_method_id": "pm_card_visa"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "succeeded"

    get_resp = await client.get(f"/api/v1/payments/{payment_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "succeeded"
    assert get_resp.json()["client_secret"] is None


@pytest.mark.e2e
async def test_payment_via_webhook(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 3000, "currency": "eur"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = payment_resp.json()["id"]

    event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded",
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = event

    webhook_resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=b'{"type":"payment_intent.succeeded"}',
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    assert webhook_resp.status_code == 200

    status_resp = await client.get(f"/api/v1/payments/{payment_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "succeeded"


@pytest.mark.e2e
async def test_payment_cancellation(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 7500, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = payment_resp.json()["id"]

    cancel_resp = await client.post(
        f"/api/v1/payments/{payment_id}/cancel",
        json={"reason": "requested_by_customer"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "canceled"


@pytest.mark.e2e
async def test_idempotency_creates_payment_once(client: AsyncClient, mock_provider: AsyncMock):
    key = str(uuid.uuid4())
    body = {"amount": 5000, "currency": "usd"}

    r1 = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": key})
    r2 = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": key})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert mock_provider.create_payment_intent.call_count == 1
