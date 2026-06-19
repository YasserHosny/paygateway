import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.providers.base import ProviderPaymentIntent
from paygateway.schemas.payment import CreatePaymentRequest
from paygateway.services.payment_service import create_payment
from paygateway.services.reconciliation_service import (
    ReconciliationError,
    run_reconciliation,
    get_report,
    list_reports,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 2, tzinfo=timezone.utc)


def _provider_pi(provider_id: str, amount: int = 5000, currency: str = "USD") -> ProviderPaymentIntent:
    return ProviderPaymentIntent(
        provider_id=provider_id,
        status="succeeded",
        amount=amount,
        currency=currency,
    )


@pytest.mark.unit
async def test_reconciliation_all_matched(db_session: AsyncSession, mock_provider: AsyncMock):
    req = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, req, f"idem-{uuid.uuid4()}")
    payment.external_id = "pi_match_1"
    payment.created_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    await db_session.flush()

    mock_provider.list_payment_intents.return_value = ([_provider_pi("pi_match_1")], None)

    report = await run_reconciliation(db_session, mock_provider, START, END)
    assert report.status == "completed"
    assert report.total_internal == 1
    assert report.total_provider == 1
    assert report.discrepancy_count == 0


@pytest.mark.unit
async def test_reconciliation_missing_provider(db_session: AsyncSession, mock_provider: AsyncMock):
    req = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, req, f"idem-{uuid.uuid4()}")
    payment.external_id = "pi_orphan"
    payment.created_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    await db_session.flush()

    mock_provider.list_payment_intents.return_value = ([], None)

    report = await run_reconciliation(db_session, mock_provider, START, END)
    assert report.discrepancy_count == 1
    assert report.discrepancies[0]["type"] == "missing_provider"


@pytest.mark.unit
async def test_reconciliation_missing_internal(db_session: AsyncSession, mock_provider: AsyncMock):
    mock_provider.list_payment_intents.return_value = ([_provider_pi("pi_provider_only")], None)

    report = await run_reconciliation(db_session, mock_provider, START, END)
    assert report.discrepancy_count == 1
    assert report.discrepancies[0]["type"] == "missing_internal"


@pytest.mark.unit
async def test_reconciliation_amount_mismatch(db_session: AsyncSession, mock_provider: AsyncMock):
    req = CreatePaymentRequest(amount=5000, currency="usd")
    payment = await create_payment(db_session, mock_provider, req, f"idem-{uuid.uuid4()}")
    payment.external_id = "pi_amt"
    payment.amount = 5000
    payment.created_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    await db_session.flush()

    mock_provider.list_payment_intents.return_value = ([_provider_pi("pi_amt", amount=9999)], None)

    report = await run_reconciliation(db_session, mock_provider, START, END)
    assert report.discrepancy_count == 1
    assert report.discrepancies[0]["type"] == "amount_mismatch"


@pytest.mark.unit
async def test_reconciliation_provider_error(db_session: AsyncSession, mock_provider: AsyncMock):
    mock_provider.list_payment_intents.side_effect = Exception("Provider unreachable")

    with pytest.raises(ReconciliationError):
        await run_reconciliation(db_session, mock_provider, START, END)


@pytest.mark.unit
async def test_get_report_not_found(db_session: AsyncSession):
    result = await get_report(db_session, uuid.uuid4())
    assert result is None


@pytest.mark.unit
async def test_list_reports_empty(db_session: AsyncSession):
    reports, total = await list_reports(db_session)
    assert reports == []
    assert total == 0


@pytest.mark.unit
async def test_reconciliation_paginated_provider(db_session: AsyncSession, mock_provider: AsyncMock):
    mock_provider.list_payment_intents.side_effect = [
        ([_provider_pi("pi_page1")], "pi_page1"),
        ([_provider_pi("pi_page2")], None),
    ]

    report = await run_reconciliation(db_session, mock_provider, START, END)
    assert report.total_provider == 2
    assert mock_provider.list_payment_intents.call_count == 2
