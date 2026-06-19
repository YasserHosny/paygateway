import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.payment import Payment
from paygateway.models.refund import Refund
from paygateway.models.webhook_event import WebhookEvent
from paygateway.providers.base import PaymentProvider, ProviderWebhookEvent
from paygateway.services import audit_service
from paygateway.services.payment_service import compute_refunded_amount

logger = structlog.get_logger()

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"processing", "requires_action", "succeeded", "failed", "canceled"},
    "processing": {"succeeded", "failed"},
    "requires_action": {"succeeded", "failed", "canceled"},
    "succeeded": {"refunded", "partially_refunded", "disputed"},
    "partially_refunded": {"refunded", "disputed"},
}


async def process_webhook(
    db: AsyncSession,
    provider: PaymentProvider,
    payload: bytes,
    headers: dict,
) -> bool:
    event = await provider.verify_webhook(payload, headers)

    existing = await db.execute(
        select(WebhookEvent).where(WebhookEvent.event_id == event.event_id)
    )
    existing_record = existing.scalar_one_or_none()

    if existing_record and existing_record.processed:
        return True

    if not existing_record:
        webhook_event = WebhookEvent(
            provider="stripe",
            event_id=event.event_id,
            event_type=event.event_type,
            payload=event.payload,
            processed=False,
        )
        db.add(webhook_event)
        await db.flush()
    else:
        webhook_event = existing_record

    try:
        await _dispatch_event(db, event)
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        webhook_event.processing_error = None
    except Exception as exc:
        webhook_event.processing_error = str(exc)
        logger.error("webhook_processing_failed", event_id=event.event_id, error=str(exc))
        raise

    await db.flush()
    return True


async def _dispatch_event(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    handlers: dict[str, object] = {
        "payment_intent.succeeded": _handle_payment_succeeded,
        "payment_intent.payment_failed": _handle_payment_failed,
        "payment_intent.canceled": _handle_payment_canceled,
        "payment_intent.processing": _handle_payment_processing,
        "payment_intent.requires_action": _handle_payment_requires_action,
        "charge.refunded": _handle_charge_refunded,
        "charge.dispute.created": _handle_dispute_created,
    }

    handler = handlers.get(event.event_type)
    if handler is None:
        logger.info("unhandled_webhook_event", event_type=event.event_type)
        return

    await handler(db, event)  # type: ignore[operator]


async def _find_payment_by_external_id(
    db: AsyncSession, external_id: str | None
) -> Payment | None:
    if not external_id:
        return None
    stmt = select(Payment).where(Payment.external_id == external_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _can_transition(current: str, target: str) -> bool:
    allowed = VALID_TRANSITIONS.get(current, set())
    return target in allowed


async def _handle_payment_succeeded(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        logger.warning("webhook_orphan_event", event_type=event.event_type, provider_id=event.payment_provider_id)
        return

    if not _can_transition(payment.status, "succeeded"):
        logger.warning("webhook_invalid_transition", current=payment.status, target="succeeded")
        return

    payment.status = "succeeded"
    payment.confirmed_at = datetime.now(timezone.utc)

    await audit_service.log_action(
        db, actor_id="stripe", actor_type="webhook",
        action="payment.confirmed_via_webhook", resource_type="payment",
        resource_id=payment.id, outcome="success",
    )


async def _handle_payment_failed(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return

    if not _can_transition(payment.status, "failed"):
        return

    data_object = event.payload.get("data", {}).get("object", {})
    last_error = data_object.get("last_payment_error", {}) or {}

    payment.status = "failed"
    payment.failure_code = last_error.get("code")
    payment.failure_message = last_error.get("message")

    await audit_service.log_action(
        db, actor_id="stripe", actor_type="webhook",
        action="payment.failed_via_webhook", resource_type="payment",
        resource_id=payment.id, outcome="failure",
        details={"failure_code": payment.failure_code},
    )


async def _handle_payment_canceled(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return

    if not _can_transition(payment.status, "canceled"):
        return

    payment.status = "canceled"
    payment.canceled_at = datetime.now(timezone.utc)

    await audit_service.log_action(
        db, actor_id="stripe", actor_type="webhook",
        action="payment.canceled_via_webhook", resource_type="payment",
        resource_id=payment.id, outcome="success",
    )


async def _handle_payment_processing(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return
    if _can_transition(payment.status, "processing"):
        payment.status = "processing"


async def _handle_payment_requires_action(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return
    if _can_transition(payment.status, "requires_action"):
        payment.status = "requires_action"


async def _handle_charge_refunded(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return

    if event.refund_provider_id:
        stmt = select(Refund).where(Refund.external_id == event.refund_provider_id)
        result = await db.execute(stmt)
        refund = result.scalar_one_or_none()
        if refund:
            refund.status = "succeeded"

    total_refunded = compute_refunded_amount(payment)
    if total_refunded >= payment.amount:
        new_status = "refunded"
    else:
        new_status = "partially_refunded"

    if _can_transition(payment.status, new_status):
        payment.status = new_status

    await audit_service.log_action(
        db, actor_id="stripe", actor_type="webhook",
        action="refund.completed_via_webhook", resource_type="payment",
        resource_id=payment.id, outcome="success",
        details={"refunded_amount": total_refunded},
    )


async def _handle_dispute_created(db: AsyncSession, event: ProviderWebhookEvent) -> None:
    payment = await _find_payment_by_external_id(db, event.payment_provider_id)
    if not payment:
        return

    if _can_transition(payment.status, "disputed"):
        payment.status = "disputed"

    await audit_service.log_action(
        db, actor_id="stripe", actor_type="webhook",
        action="payment.disputed", resource_type="payment",
        resource_id=payment.id, outcome="failure",
        details=event.payload.get("data", {}).get("object", {}),
    )
