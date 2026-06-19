import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.payment import Payment
from paygateway.models.refund import Refund
from paygateway.providers.base import PaymentProvider, ProviderError
from paygateway.schemas.payment import CreatePaymentRequest, PaymentListFilters
from paygateway.services import audit_service

CANCELABLE_STATUSES = {"pending", "requires_action", "processing"}


class PaymentNotFoundError(Exception):
    pass


class PaymentNotCancelableError(Exception):
    pass


class PaymentProviderError(Exception):
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code
        super().__init__(message)


async def create_payment(
    db: AsyncSession,
    provider: PaymentProvider,
    request: CreatePaymentRequest,
    idempotency_key: str,
    actor_id: str = "system",
    ip_address: str | None = None,
) -> Payment:
    existing = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
    existing_payment = existing.scalar_one_or_none()
    if existing_payment is not None:
        return existing_payment

    try:
        pi = await provider.create_payment_intent(
            amount=request.amount,
            currency=request.currency,
            idempotency_key=idempotency_key,
            customer_id=request.customer_id,
            description=request.description,
            metadata=request.metadata,
        )
    except ProviderError as e:
        raise PaymentProviderError(e.message, e.code) from e

    payment = Payment(
        external_id=pi.provider_id,
        provider="stripe",
        status=pi.status,
        amount=pi.amount,
        currency=pi.currency,
        customer_id=request.customer_id,
        provider_customer_id=pi.provider_customer_id,
        metadata_=request.metadata or {},
        idempotency_key=idempotency_key,
        client_secret=pi.client_secret,
        description=request.description,
    )
    db.add(payment)
    await db.flush()

    await audit_service.log_action(
        db,
        actor_id=actor_id,
        actor_type="user",
        action="payment.created",
        resource_type="payment",
        resource_id=payment.id,
        details={"amount": payment.amount, "currency": payment.currency},
        ip_address=ip_address,
    )

    return payment


async def get_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await db.execute(stmt)
    payment = result.scalar_one_or_none()
    if payment is None:
        raise PaymentNotFoundError(f"Payment {payment_id} not found")
    return payment


async def list_payments(
    db: AsyncSession,
    filters: PaymentListFilters,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Payment], int]:
    stmt = select(Payment)
    count_stmt = select(func.count(Payment.id))

    if filters.status:
        stmt = stmt.where(Payment.status == filters.status)
        count_stmt = count_stmt.where(Payment.status == filters.status)
    if filters.customer_id:
        stmt = stmt.where(Payment.customer_id == filters.customer_id)
        count_stmt = count_stmt.where(Payment.customer_id == filters.customer_id)
    if filters.currency:
        stmt = stmt.where(Payment.currency == filters.currency.upper())
        count_stmt = count_stmt.where(Payment.currency == filters.currency.upper())
    if filters.created_after:
        stmt = stmt.where(Payment.created_at >= filters.created_after)
        count_stmt = count_stmt.where(Payment.created_at >= filters.created_after)
    if filters.created_before:
        stmt = stmt.where(Payment.created_at < filters.created_before)
        count_stmt = count_stmt.where(Payment.created_at < filters.created_before)

    stmt = stmt.order_by(Payment.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    payments = list(result.scalars().all())

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return payments, total


async def confirm_payment(
    db: AsyncSession,
    provider: PaymentProvider,
    payment_id: uuid.UUID,
    payment_method_id: str,
    idempotency_key: str,
    actor_id: str = "system",
    ip_address: str | None = None,
) -> Payment:
    payment = await get_payment(db, payment_id)

    try:
        pi = await provider.confirm_payment_intent(
            provider_payment_id=payment.external_id,  # type: ignore[arg-type]
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
        )
    except ProviderError as e:
        raise PaymentProviderError(e.message, e.code) from e

    payment.status = pi.status
    if pi.status == "succeeded":
        payment.confirmed_at = datetime.now(timezone.utc)
    payment.failure_code = pi.failure_code
    payment.failure_message = pi.failure_message
    await db.flush()

    await audit_service.log_action(
        db,
        actor_id=actor_id,
        actor_type="user",
        action="payment.confirmed",
        resource_type="payment",
        resource_id=payment.id,
        details={"status": payment.status},
        ip_address=ip_address,
    )

    return payment


async def cancel_payment(
    db: AsyncSession,
    provider: PaymentProvider,
    payment_id: uuid.UUID,
    idempotency_key: str,
    reason: str | None = None,
    actor_id: str = "system",
    ip_address: str | None = None,
) -> Payment:
    payment = await get_payment(db, payment_id)

    if payment.status not in CANCELABLE_STATUSES:
        raise PaymentNotCancelableError(
            f"Payment in status '{payment.status}' cannot be canceled"
        )

    try:
        pi = await provider.cancel_payment_intent(
            provider_payment_id=payment.external_id,  # type: ignore[arg-type]
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except ProviderError as e:
        raise PaymentProviderError(e.message, e.code) from e

    payment.status = pi.status
    payment.canceled_at = datetime.now(timezone.utc)
    await db.flush()

    await audit_service.log_action(
        db,
        actor_id=actor_id,
        actor_type="user",
        action="payment.canceled",
        resource_type="payment",
        resource_id=payment.id,
        details={"reason": reason},
        ip_address=ip_address,
    )

    return payment


def compute_refunded_amount(payment: Payment) -> int:
    from sqlalchemy.orm import attributes
    history = attributes.instance_state(payment)
    if "refunds" not in history.dict:
        return 0
    return sum(
        r.amount for r in payment.refunds if r.status == "succeeded"
    )
