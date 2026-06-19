import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.payment import Payment
from paygateway.providers.base import ProviderError, ProviderPaymentIntent
from paygateway.schemas.payment import CreatePaymentRequest, PaymentListFilters
from paygateway.services.payment_service import (
    PaymentNotCancelableError,
    PaymentNotFoundError,
    PaymentProviderError,
    cancel_payment,
    confirm_payment,
    create_payment,
    get_payment,
    list_payments,
)


@pytest.mark.unit
async def test_create_payment_success(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-1")
    await db_session.commit()

    assert payment.amount == 5000
    assert payment.currency == "USD"
    assert payment.status == "pending"
    assert payment.external_id == "pi_test_123"
    assert payment.client_secret == "pi_test_123_secret_abc"
    mock_provider.create_payment_intent.assert_called_once()


@pytest.mark.unit
async def test_create_payment_provider_error(db_session: AsyncSession, mock_provider: AsyncMock):
    mock_provider.create_payment_intent.side_effect = ProviderError("fail", "stripe")
    request = CreatePaymentRequest(amount=5000, currency="usd")
    with pytest.raises(PaymentProviderError):
        await create_payment(db_session, mock_provider, request, "idem-2")


@pytest.mark.unit
async def test_get_payment_not_found(db_session: AsyncSession):
    with pytest.raises(PaymentNotFoundError):
        await get_payment(db_session, uuid.uuid4())


@pytest.mark.unit
async def test_cancel_payment_wrong_status(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-3")
    payment.status = "succeeded"
    await db_session.commit()

    with pytest.raises(PaymentNotCancelableError):
        await cancel_payment(db_session, mock_provider, payment.id, "idem-cancel-3")


@pytest.mark.unit
async def test_cancel_payment_success(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-4")
    await db_session.commit()

    canceled = await cancel_payment(db_session, mock_provider, payment.id, "idem-cancel-4")
    assert canceled.status == "canceled"


# ---------------------------------------------------------------------------
# confirm_payment
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_confirm_payment_updates_status(db_session: AsyncSession, mock_provider: AsyncMock):
    payment = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=5000, currency="usd"),
        "idem-conf-1",
    )
    await db_session.flush()

    confirmed = await confirm_payment(
        db_session, mock_provider,
        payment.id,
        payment_method_id="pm_card_visa",
        idempotency_key="idem-conf-key-1",
    )

    assert confirmed.status == "succeeded"
    assert confirmed.confirmed_at is not None
    mock_provider.confirm_payment_intent.assert_called_once()


@pytest.mark.unit
async def test_confirm_payment_not_found(db_session: AsyncSession, mock_provider: AsyncMock):
    with pytest.raises(PaymentNotFoundError):
        await confirm_payment(
            db_session, mock_provider,
            uuid.uuid4(),
            payment_method_id="pm_card_visa",
            idempotency_key="idem-conf-missing",
        )


# ---------------------------------------------------------------------------
# list_payments
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_list_payments_returns_all(db_session: AsyncSession, mock_provider: AsyncMock):
    for i in range(3):
        await create_payment(
            db_session, mock_provider,
            CreatePaymentRequest(amount=1000 * (i + 1), currency="usd"),
            f"idem-la-{i}",
        )
    await db_session.flush()

    payments, total = await list_payments(db_session, PaymentListFilters(), limit=10, offset=0)
    assert total == 3
    assert len(payments) == 3


@pytest.mark.unit
async def test_list_payments_filter_by_status(db_session: AsyncSession, mock_provider: AsyncMock):
    p1 = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=1000, currency="usd"),
        "idem-ls-1",
    )
    p2 = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=2000, currency="usd"),
        "idem-ls-2",
    )
    p2.status = "canceled"
    await db_session.flush()

    payments, total = await list_payments(
        db_session, PaymentListFilters(status="pending"), limit=10, offset=0
    )
    assert total == 1
    assert payments[0].id == p1.id


@pytest.mark.unit
async def test_list_payments_filter_by_currency(db_session: AsyncSession, mock_provider: AsyncMock):
    await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=1000, currency="usd"),
        "idem-lc-1",
    )
    p2 = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=2000, currency="eur"),
        "idem-lc-2",
    )
    await db_session.flush()

    payments, total = await list_payments(
        db_session, PaymentListFilters(currency="eur"), limit=10, offset=0
    )
    assert total == 1
    assert payments[0].currency == "EUR"


@pytest.mark.unit
async def test_list_payments_pagination(db_session: AsyncSession, mock_provider: AsyncMock):
    for i in range(5):
        await create_payment(
            db_session, mock_provider,
            CreatePaymentRequest(amount=500, currency="usd"),
            f"idem-lp-{i}",
        )
    await db_session.flush()

    page1, total = await list_payments(db_session, PaymentListFilters(), limit=2, offset=0)
    page2, _ = await list_payments(db_session, PaymentListFilters(), limit=2, offset=2)

    assert total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


@pytest.mark.unit
async def test_create_payment_idempotency_returns_same_record(
    db_session: AsyncSession, mock_provider: AsyncMock
):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    p1 = await create_payment(db_session, mock_provider, request, "idem-dup")
    await db_session.flush()
    p2 = await create_payment(db_session, mock_provider, request, "idem-dup")

    assert p1.id == p2.id
    assert mock_provider.create_payment_intent.call_count == 1
