import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.payment import Payment
from paygateway.providers.base import (
    ProviderWebhookEvent,
    ProviderWebhookVerificationError,
)
from paygateway.schemas.payment import CreatePaymentRequest
from paygateway.services import webhook_service
from paygateway.services.payment_service import create_payment


async def _make_payment(db: AsyncSession, mock_provider: AsyncMock, status: str = "pending") -> Payment:
    req = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db, mock_provider, req, f"idem-{uuid.uuid4()}")
    payment.external_id = "pi_test_123"
    payment.status = status
    await db.flush()
    return payment


def _make_event(event_type: str, payment_provider_id: str | None = "pi_test_123", event_id: str | None = None) -> ProviderWebhookEvent:
    return ProviderWebhookEvent(
        event_id=event_id or f"evt_{uuid.uuid4().hex[:8]}",
        event_type=event_type,
        payload={"data": {"object": {"id": payment_provider_id, "last_payment_error": None}}},
        payment_provider_id=payment_provider_id,
    )


@pytest.mark.unit
async def test_process_webhook_payment_succeeded(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await _make_payment(db_session, mock_provider, "pending")
    event = _make_event("payment_intent.succeeded")
    mock_provider.verify_webhook.return_value = event

    await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    await db_session.refresh(payment)
    assert payment.status == "succeeded"
    assert payment.confirmed_at is not None


@pytest.mark.unit
async def test_process_webhook_payment_failed(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await _make_payment(db_session, mock_provider, "pending")
    event = ProviderWebhookEvent(
        event_id="evt_fail",
        event_type="payment_intent.payment_failed",
        payload={"data": {"object": {"last_payment_error": {"code": "card_declined", "message": "Declined"}}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = event

    await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    await db_session.refresh(payment)
    assert payment.status == "failed"


@pytest.mark.unit
async def test_process_webhook_payment_canceled(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await _make_payment(db_session, mock_provider, "pending")
    event = _make_event("payment_intent.canceled")
    mock_provider.verify_webhook.return_value = event

    await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    await db_session.refresh(payment)
    assert payment.status == "canceled"


@pytest.mark.unit
async def test_process_webhook_idempotent(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await _make_payment(db_session, mock_provider, "pending")
    event = _make_event("payment_intent.succeeded", event_id="evt_dedup")
    mock_provider.verify_webhook.return_value = event

    await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    result = await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    assert result is True
    assert mock_provider.verify_webhook.call_count == 2


@pytest.mark.unit
async def test_process_webhook_unknown_payment(db_session: AsyncSession, mock_provider: AsyncMock):
    event = _make_event("payment_intent.succeeded", payment_provider_id="pi_unknown")
    mock_provider.verify_webhook.return_value = event
    result = await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    assert result is True


@pytest.mark.unit
async def test_process_webhook_unhandled_event_type(db_session: AsyncSession, mock_provider: AsyncMock):
    event = _make_event("customer.created", payment_provider_id=None)
    mock_provider.verify_webhook.return_value = event
    result = await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    assert result is True


@pytest.mark.unit
async def test_process_webhook_invalid_transition(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await _make_payment(db_session, mock_provider, "succeeded")
    event = _make_event("payment_intent.succeeded")
    mock_provider.verify_webhook.return_value = event

    await webhook_service.process_webhook(db_session, mock_provider, b"payload", {})
    await db_session.refresh(payment)
    assert payment.status == "succeeded"


@pytest.mark.unit
def test_valid_transitions_defined():
    assert "pending" in webhook_service.VALID_TRANSITIONS
    assert "succeeded" in webhook_service.VALID_TRANSITIONS["pending"]
    assert "failed" in webhook_service.VALID_TRANSITIONS["pending"]
