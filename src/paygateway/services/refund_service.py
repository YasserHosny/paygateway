import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.refund import Refund
from paygateway.providers.base import PaymentProvider, ProviderError
from paygateway.services import audit_service
from paygateway.services.payment_service import (
    PaymentNotFoundError,
    PaymentProviderError,
    compute_refunded_amount,
    get_payment,
)

REFUNDABLE_STATUSES = {"succeeded", "partially_refunded"}


class PaymentNotRefundableError(Exception):
    pass


class RefundExceedsAmountError(Exception):
    pass


class RefundNotFoundError(Exception):
    pass


async def create_refund(
    db: AsyncSession,
    provider: PaymentProvider,
    payment_id: uuid.UUID,
    idempotency_key: str,
    amount: int | None = None,
    reason: str | None = None,
    actor_id: str = "system",
    ip_address: str | None = None,
) -> Refund:
    payment = await get_payment(db, payment_id)

    if payment.status not in REFUNDABLE_STATUSES:
        raise PaymentNotRefundableError(
            f"Payment in status '{payment.status}' is not refundable"
        )

    already_refunded = compute_refunded_amount(payment)
    max_refundable = payment.amount - already_refunded

    if amount is None:
        amount = max_refundable
    elif amount > max_refundable:
        raise RefundExceedsAmountError(
            f"Refund amount {amount} exceeds remaining refundable amount {max_refundable}"
        )

    try:
        provider_refund = await provider.create_refund(
            provider_payment_id=payment.external_id,  # type: ignore[arg-type]
            amount=amount,
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except ProviderError as e:
        raise PaymentProviderError(e.message, e.code) from e

    refund = Refund(
        payment_id=payment_id,
        external_id=provider_refund.provider_id,
        amount=amount,
        reason=reason,
        status=provider_refund.status,
        idempotency_key=idempotency_key,
    )
    db.add(refund)
    await db.flush()

    await audit_service.log_action(
        db,
        actor_id=actor_id,
        actor_type="user",
        action="refund.created",
        resource_type="refund",
        resource_id=refund.id,
        details={
            "payment_id": str(payment_id),
            "amount": amount,
            "reason": reason,
        },
        ip_address=ip_address,
    )

    return refund


async def get_refund(db: AsyncSession, refund_id: uuid.UUID) -> Refund:
    stmt = select(Refund).where(Refund.id == refund_id)
    result = await db.execute(stmt)
    refund = result.scalar_one_or_none()
    if refund is None:
        raise RefundNotFoundError(f"Refund {refund_id} not found")
    return refund


async def list_refunds_for_payment(
    db: AsyncSession,
    payment_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Refund], int]:
    # Verify payment exists
    await get_payment(db, payment_id)

    stmt = (
        select(Refund)
        .where(Refund.payment_id == payment_id)
        .order_by(Refund.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count(Refund.id)).where(Refund.payment_id == payment_id)

    result = await db.execute(stmt)
    refunds = list(result.scalars().all())

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return refunds, total
