"""
E2E tests for error scenarios: declines, invalid requests, duplicate keys, over-refunds.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from paygateway.providers.base import (
    ProviderError,
    ProviderWebhookEvent,
    ProviderWebhookVerificationError,
)


@pytest.mark.e2e
async def test_provider_error_on_create(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.create_payment_intent.side_effect = ProviderError("Card declined", "stripe", code="card_declined")
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"]["code"] == "PROVIDER_ERROR"


@pytest.mark.e2e
async def test_invalid_amount_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 0, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_invalid_currency_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "XYZ_INVALID"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_over_refund_rejected(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
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
    await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 9999},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "REFUND_EXCEEDS_AMOUNT"


@pytest.mark.e2e
async def test_cancel_already_succeeded_payment(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
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
    await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )

    cancel_resp = await client.post(
        f"/api/v1/payments/{payment_id}/cancel",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert cancel_resp.status_code == 409
    assert cancel_resp.json()["detail"]["error"]["code"] == "PAYMENT_NOT_CANCELABLE"


@pytest.mark.e2e
async def test_webhook_invalid_signature_rejected(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.verify_webhook.side_effect = ProviderWebhookVerificationError("bad sig", "stripe")
    resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=b"tampered_payload",
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert resp.status_code == 400


@pytest.mark.e2e
async def test_unauthenticated_requests_rejected(client: AsyncClient):
    client.headers.pop("X-API-Key", None)

    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 401

    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
