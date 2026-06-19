import json

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from paygateway.providers.base import (
    ProviderWebhookEvent,
    ProviderWebhookVerificationError,
)


def _make_event(event_type: str = "payment_intent.succeeded") -> ProviderWebhookEvent:
    return ProviderWebhookEvent(
        event_id="evt_test_001",
        event_type=event_type,
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )


@pytest.mark.integration
async def test_webhook_valid_event(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.verify_webhook.return_value = _make_event()
    resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=json.dumps({"type": "payment_intent.succeeded"}).encode(),
        headers={"stripe-signature": "t=1,v1=valid", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


@pytest.mark.integration
async def test_webhook_invalid_signature(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.verify_webhook.side_effect = ProviderWebhookVerificationError("bad sig", "stripe")
    resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=b"payload",
        headers={"stripe-signature": "invalid"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


@pytest.mark.integration
async def test_webhook_idempotent_duplicate(client: AsyncClient, mock_provider: AsyncMock):
    event = _make_event()
    mock_provider.verify_webhook.return_value = event

    resp1 = await client.post(
        "/api/v1/webhooks/stripe",
        content=b"payload",
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    resp2 = await client.post(
        "/api/v1/webhooks/stripe",
        content=b"payload",
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200


@pytest.mark.integration
async def test_webhook_no_auth_required(client: AsyncClient, mock_provider: AsyncMock):
    """Webhook endpoint must not require API key auth."""
    mock_provider.verify_webhook.return_value = _make_event()
    unauthenticated = client
    unauthenticated.headers.pop("X-API-Key", None)
    resp = await unauthenticated.post(
        "/api/v1/webhooks/stripe",
        content=b"payload",
        headers={"stripe-signature": "t=1,v1=sig"},
    )
    assert resp.status_code == 200
