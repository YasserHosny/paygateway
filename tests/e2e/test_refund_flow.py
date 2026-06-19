"""
E2E tests for the complete refund lifecycle.
Flow: create payment → mark succeeded → refund → webhook → verify.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from paygateway.providers.base import ProviderRefund, ProviderWebhookEvent


@pytest.mark.e2e
async def test_full_refund_lifecycle(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert payment_resp.status_code == 201
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

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_full",
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
    refund_id = refund_resp.json()["id"]
    assert refund_resp.json()["amount"] == 5000

    refund_event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="charge.refunded",
        payload={"data": {"object": {"id": "ch_123", "payment_intent": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
        refund_provider_id="re_full",
    )
    mock_provider.verify_webhook.return_value = refund_event
    await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )

    payment_status_resp = await client.get(f"/api/v1/payments/{payment_id}")
    assert payment_status_resp.status_code == 200

    refund_status_resp = await client.get(f"/api/v1/refunds/{refund_id}")
    assert refund_status_resp.status_code == 200


@pytest.mark.e2e
async def test_consecutive_partial_refunds(client: AsyncClient, mock_provider: AsyncMock):
    """Two sequential partial refunds on the same payment both succeed."""
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 10000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert payment_resp.status_code == 201
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

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_first_partial",
        payment_provider_id="pi_test_123",
        amount=4000,
        currency="USD",
        status="pending",
    )
    r1 = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 4000},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r1.status_code == 201
    assert r1.json()["amount"] == 4000

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_second_partial",
        payment_provider_id="pi_test_123",
        amount=6000,
        currency="USD",
        status="pending",
    )
    r2 = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 6000},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r2.status_code == 201
    assert r2.json()["amount"] == 6000

    refunds_resp = await client.get(f"/api/v1/payments/{payment_id}/refunds")
    assert refunds_resp.status_code == 200
    assert refunds_resp.json()["pagination"]["total"] == 2


@pytest.mark.e2e
async def test_refund_webhook_updates_refund_status_to_succeeded(
    client: AsyncClient, mock_provider: AsyncMock
):
    """charge.refunded webhook must transition the matching Refund to status=succeeded."""
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert payment_resp.status_code == 201
    payment_id = payment_resp.json()["id"]

    # Mark payment succeeded
    success_event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded",
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = success_event
    await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )

    # Create refund — provider assigns external id "re_via_webhook"
    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_via_webhook",
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
    refund_id = refund_resp.json()["id"]
    assert refund_resp.json()["status"] == "pending"

    # Fire charge.refunded webhook referencing the same refund provider id
    refund_event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="charge.refunded",
        payload={"data": {"object": {"id": "ch_test", "payment_intent": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
        refund_provider_id="re_via_webhook",
    )
    mock_provider.verify_webhook.return_value = refund_event
    wh_resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    assert wh_resp.status_code == 200

    # Refund must now be succeeded
    get_resp = await client.get(f"/api/v1/refunds/{refund_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "succeeded"


@pytest.mark.e2e
async def test_partial_refund(client: AsyncClient, mock_provider: AsyncMock):
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 10000, "currency": "usd"},
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

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_partial",
        payment_provider_id="pi_test_123",
        amount=3000,
        currency="USD",
        status="pending",
    )
    refund_resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 3000},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refund_resp.status_code == 201
    assert refund_resp.json()["amount"] == 3000
