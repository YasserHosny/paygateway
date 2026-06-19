import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.schemas.payment import CreatePaymentRequest
from paygateway.services.payment_service import create_payment
from paygateway.services.refund_service import (
    PaymentNotRefundableError,
    RefundExceedsAmountError,
    RefundNotFoundError,
    create_refund,
    get_refund,
)


@pytest.mark.unit
async def test_create_full_refund(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-r1")
    payment.status = "succeeded"
    await db_session.commit()

    refund = await create_refund(db_session, mock_provider, payment.id, "idem-ref-1")
    assert refund.amount == 5000
    assert refund.status == "pending"


@pytest.mark.unit
async def test_create_partial_refund(db_session: AsyncSession, mock_provider: AsyncMock):
    from paygateway.providers.base import ProviderRefund

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_partial",
        payment_provider_id="pi_test_123",
        amount=2000,
        currency="USD",
        status="pending",
    )
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-r2")
    payment.status = "succeeded"
    await db_session.commit()

    refund = await create_refund(db_session, mock_provider, payment.id, "idem-ref-2", amount=2000)
    assert refund.amount == 2000


@pytest.mark.unit
async def test_refund_non_refundable_status(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-r3")
    await db_session.commit()

    with pytest.raises(PaymentNotRefundableError):
        await create_refund(db_session, mock_provider, payment.id, "idem-ref-3")


@pytest.mark.unit
async def test_refund_exceeds_amount(db_session: AsyncSession, mock_provider: AsyncMock):
    request = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, request, "idem-r4")
    payment.status = "succeeded"
    await db_session.commit()

    with pytest.raises(RefundExceedsAmountError):
        await create_refund(db_session, mock_provider, payment.id, "idem-ref-4", amount=9999)


@pytest.mark.unit
async def test_get_refund_not_found(db_session: AsyncSession):
    with pytest.raises(RefundNotFoundError):
        await get_refund(db_session, uuid.uuid4())


# ---------------------------------------------------------------------------
# list_refunds_for_payment
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_list_refunds_empty_for_succeeded_payment(
    db_session: AsyncSession, mock_provider: AsyncMock
):
    from paygateway.services.refund_service import list_refunds_for_payment

    payment = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=5000, currency="usd"),
        "idem-lr-1",
    )
    payment.status = "succeeded"
    await db_session.flush()

    refunds, total = await list_refunds_for_payment(db_session, payment.id)
    assert total == 0
    assert refunds == []


@pytest.mark.unit
async def test_list_refunds_returns_created_refund(
    db_session: AsyncSession, mock_provider: AsyncMock
):
    from paygateway.providers.base import ProviderRefund
    from paygateway.services.refund_service import create_refund, list_refunds_for_payment

    payment = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=10000, currency="usd"),
        "idem-lr-2",
    )
    payment.status = "succeeded"
    await db_session.flush()

    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_list_1",
        payment_provider_id="pi_test_123",
        amount=3000,
        currency="USD",
        status="pending",
    )
    await create_refund(db_session, mock_provider, payment.id, "idem-ref-lr-1", amount=3000)
    await db_session.flush()

    refunds, total = await list_refunds_for_payment(db_session, payment.id)
    assert total == 1
    assert refunds[0].amount == 3000


@pytest.mark.unit
async def test_list_refunds_for_nonexistent_payment(db_session: AsyncSession):
    from paygateway.services.payment_service import PaymentNotFoundError
    from paygateway.services.refund_service import list_refunds_for_payment

    with pytest.raises(PaymentNotFoundError):
        await list_refunds_for_payment(db_session, uuid.uuid4())


@pytest.mark.unit
async def test_list_refunds_pagination(db_session: AsyncSession, mock_provider: AsyncMock):
    from paygateway.providers.base import ProviderRefund
    from paygateway.services.refund_service import create_refund, list_refunds_for_payment

    payment = await create_payment(
        db_session, mock_provider,
        CreatePaymentRequest(amount=15000, currency="usd"),
        "idem-lr-3",
    )
    payment.status = "succeeded"
    await db_session.flush()

    for i in range(3):
        mock_provider.create_refund.return_value = ProviderRefund(
            provider_id=f"re_page_{i}",
            payment_provider_id="pi_test_123",
            amount=1000,
            currency="USD",
            status="pending",
        )
        await create_refund(
            db_session, mock_provider, payment.id, f"idem-ref-page-{i}", amount=1000
        )
    await db_session.flush()

    page1, total = await list_refunds_for_payment(db_session, payment.id, limit=2, offset=0)
    assert total == 3
    assert len(page1) == 2
