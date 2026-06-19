from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import stripe

from paygateway.providers.stripe_provider import (
    STRIPE_PAYMENT_STATUS_MAP,
    STRIPE_REFUND_STATUS_MAP,
    StripeProvider,
)
from paygateway.providers.base import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderPaymentIntent,
    ProviderRefund,
    ProviderValidationError,
    ProviderWebhookVerificationError,
)


def _make_settings():
    s = MagicMock()
    s.STRIPE_SECRET_KEY = "sk_test_fake"
    s.STRIPE_WEBHOOK_SECRET = "whsec_fake"
    s.STRIPE_API_VERSION = "2024-12-18"
    return s


def _make_pi(
    id="pi_123",
    status="requires_payment_method",
    amount=5000,
    currency="usd",
    client_secret="pi_123_secret",
    customer=None,
    last_payment_error=None,
    created=1700000000,
    metadata=None,
):
    pi = MagicMock()
    pi.id = id
    pi.status = status
    pi.amount = amount
    pi.currency = currency
    pi.client_secret = client_secret
    pi.customer = customer
    pi.last_payment_error = last_payment_error
    pi.created = created
    pi.metadata = metadata or {}
    return pi


def _make_refund(
    id="re_123",
    payment_intent="pi_123",
    amount=5000,
    currency="usd",
    status="pending",
    failure_reason=None,
    created=1700000000,
):
    r = MagicMock()
    r.id = id
    r.payment_intent = payment_intent
    r.amount = amount
    r.currency = currency
    r.status = status
    r.failure_reason = failure_reason
    r.created = created
    return r


@pytest.mark.unit
async def test_create_payment_intent_success():
    provider = StripeProvider(_make_settings())
    pi = _make_pi()
    with patch("stripe.PaymentIntent.create", return_value=pi):
        result = await provider.create_payment_intent(5000, "usd", "idem-1")
    assert result.provider_id == "pi_123"
    assert result.amount == 5000
    assert result.currency == "USD"
    assert result.status == "pending"
    assert result.client_secret == "pi_123_secret"


@pytest.mark.unit
async def test_create_payment_intent_with_metadata():
    provider = StripeProvider(_make_settings())
    pi = _make_pi(metadata={"order_id": "ord-1"})
    with patch("stripe.PaymentIntent.create", return_value=pi) as mock_create:
        await provider.create_payment_intent(
            5000, "usd", "idem-1",
            customer_id="cus_1",
            description="Test order",
            metadata={"order_id": "ord-1"},
        )
    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["customer"] == "cus_1"
    assert call_kwargs["description"] == "Test order"
    assert call_kwargs["metadata"] == {"order_id": "ord-1"}


@pytest.mark.unit
async def test_create_payment_intent_auth_error():
    provider = StripeProvider(_make_settings())
    with patch("stripe.PaymentIntent.create", side_effect=stripe.AuthenticationError()):
        with pytest.raises(ProviderAuthenticationError):
            await provider.create_payment_intent(5000, "usd", "idem-1")


@pytest.mark.unit
async def test_create_payment_intent_invalid_request():
    provider = StripeProvider(_make_settings())
    with patch("stripe.PaymentIntent.create", side_effect=stripe.InvalidRequestError("bad", "param")):
        with pytest.raises(ProviderValidationError):
            await provider.create_payment_intent(5000, "usd", "idem-1")


@pytest.mark.unit
async def test_create_payment_intent_connection_error():
    provider = StripeProvider(_make_settings())
    with patch("stripe.PaymentIntent.create", side_effect=stripe.APIConnectionError("no conn")):
        with pytest.raises(ProviderConnectionError):
            await provider.create_payment_intent(5000, "usd", "idem-1")


@pytest.mark.unit
async def test_cancel_payment_intent_success():
    provider = StripeProvider(_make_settings())
    pi = _make_pi(status="canceled")
    with patch("stripe.PaymentIntent.cancel", return_value=pi):
        result = await provider.cancel_payment_intent("pi_123", "idem-cancel")
    assert result.status == "canceled"


@pytest.mark.unit
async def test_cancel_payment_intent_valid_reason():
    provider = StripeProvider(_make_settings())
    pi = _make_pi(status="canceled")
    with patch("stripe.PaymentIntent.cancel", return_value=pi) as mock_cancel:
        await provider.cancel_payment_intent("pi_123", "idem-cancel", reason="fraudulent")
    call_kwargs = mock_cancel.call_args[1]
    assert call_kwargs["cancellation_reason"] == "fraudulent"


@pytest.mark.unit
async def test_cancel_payment_intent_invalid_reason_defaults():
    provider = StripeProvider(_make_settings())
    pi = _make_pi(status="canceled")
    with patch("stripe.PaymentIntent.cancel", return_value=pi) as mock_cancel:
        await provider.cancel_payment_intent("pi_123", "idem-cancel", reason="unknown_reason")
    call_kwargs = mock_cancel.call_args[1]
    assert call_kwargs["cancellation_reason"] == "requested_by_customer"


@pytest.mark.unit
async def test_create_refund_success():
    provider = StripeProvider(_make_settings())
    refund = _make_refund()
    with patch("stripe.Refund.create", return_value=refund):
        result = await provider.create_refund("pi_123", 5000, "idem-refund")
    assert result.provider_id == "re_123"
    assert result.amount == 5000
    assert result.status == "pending"


@pytest.mark.unit
async def test_create_refund_full_amount():
    provider = StripeProvider(_make_settings())
    refund = _make_refund()
    with patch("stripe.Refund.create", return_value=refund) as mock_create:
        await provider.create_refund("pi_123", None, "idem-refund")
    call_kwargs = mock_create.call_args[1]
    assert "amount" not in call_kwargs


@pytest.mark.unit
async def test_verify_webhook_missing_signature():
    provider = StripeProvider(_make_settings())
    with pytest.raises(ProviderWebhookVerificationError, match="Missing"):
        await provider.verify_webhook(b"payload", {})


@pytest.mark.unit
async def test_verify_webhook_invalid_signature():
    provider = StripeProvider(_make_settings())
    with patch(
        "stripe.Webhook.construct_event",
        side_effect=stripe.SignatureVerificationError("bad sig", "sig_header"),
    ):
        with pytest.raises(ProviderWebhookVerificationError):
            await provider.verify_webhook(b"payload", {"stripe-signature": "t=1,v1=bad"})


@pytest.mark.unit
async def test_verify_webhook_payment_intent_event():
    provider = StripeProvider(_make_settings())
    event = {
        "id": "evt_123",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_123"}},
    }
    with patch("stripe.Webhook.construct_event", return_value=event):
        result = await provider.verify_webhook(b"payload", {"stripe-signature": "t=1,v1=sig"})
    assert result.event_id == "evt_123"
    assert result.event_type == "payment_intent.succeeded"
    assert result.payment_provider_id == "pi_123"


@pytest.mark.unit
def test_payment_status_mapping_coverage():
    stripe_statuses = [
        "requires_payment_method", "requires_confirmation",
        "requires_action", "processing", "requires_capture",
        "succeeded", "canceled",
    ]
    for s in stripe_statuses:
        assert s in STRIPE_PAYMENT_STATUS_MAP


@pytest.mark.unit
def test_refund_status_mapping_coverage():
    stripe_statuses = ["pending", "succeeded", "failed", "canceled"]
    for s in stripe_statuses:
        assert s in STRIPE_REFUND_STATUS_MAP


@pytest.mark.unit
async def test_list_payment_intents_no_more():
    provider = StripeProvider(_make_settings())
    pi = _make_pi()
    mock_result = MagicMock()
    mock_result.data = [pi]
    mock_result.has_more = False
    with patch("stripe.PaymentIntent.list", return_value=mock_result):
        intents, cursor = await provider.list_payment_intents(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
    assert len(intents) == 1
    assert cursor is None


@pytest.mark.unit
async def test_list_payment_intents_has_more():
    provider = StripeProvider(_make_settings())
    pi = _make_pi()
    mock_result = MagicMock()
    mock_result.data = [pi]
    mock_result.has_more = True
    with patch("stripe.PaymentIntent.list", return_value=mock_result):
        intents, cursor = await provider.list_payment_intents(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
    assert cursor == "pi_123"
