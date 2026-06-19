from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.payment import Payment
from paygateway.models.reconciliation_report import ReconciliationReport
from paygateway.providers.base import PaymentProvider
from paygateway.services import audit_service


class ReconciliationError(Exception):
    pass


async def run_reconciliation(
    db: AsyncSession,
    provider: PaymentProvider,
    date_range_start: datetime,
    date_range_end: datetime,
    actor_id: str = "system",
) -> ReconciliationReport:
    report = ReconciliationReport(
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        total_internal=0,
        total_provider=0,
        matched_count=0,
        discrepancy_count=0,
        status="in_progress",
    )
    db.add(report)
    await db.flush()

    try:
        stmt = select(Payment).where(
            Payment.created_at >= date_range_start,
            Payment.created_at < date_range_end,
            Payment.external_id.isnot(None),
        )
        result = await db.execute(stmt)
        internal_payments = list(result.scalars().all())

        internal_map: dict[str, Payment] = {}
        for p in internal_payments:
            if p.external_id:
                internal_map[p.external_id] = p

        provider_map: dict[str, object] = {}
        cursor = None
        while True:
            intents, next_cursor = await provider.list_payment_intents(
                created_after=date_range_start,
                created_before=date_range_end,
                limit=100,
                starting_after=cursor,
            )
            for pi in intents:
                provider_map[pi.provider_id] = pi
            if next_cursor is None:
                break
            cursor = next_cursor

        discrepancies: list[dict] = []

        for ext_id, payment in internal_map.items():
            pi = provider_map.get(ext_id)
            if pi is None:
                discrepancies.append({
                    "type": "missing_provider",
                    "internal_id": str(payment.id),
                    "provider_id": ext_id,
                    "details": "Payment exists internally but not at provider.",
                })
                continue

            if payment.amount != pi.amount:  # type: ignore[union-attr]
                discrepancies.append({
                    "type": "amount_mismatch",
                    "internal_id": str(payment.id),
                    "provider_id": ext_id,
                    "field": "amount",
                    "internal_value": str(payment.amount),
                    "provider_value": str(pi.amount),  # type: ignore[union-attr]
                    "details": "Amount mismatch.",
                })

            if payment.currency != pi.currency:  # type: ignore[union-attr]
                discrepancies.append({
                    "type": "currency_mismatch",
                    "internal_id": str(payment.id),
                    "provider_id": ext_id,
                    "field": "currency",
                    "internal_value": payment.currency,
                    "provider_value": pi.currency,  # type: ignore[union-attr]
                    "details": "Currency mismatch.",
                })

        for provider_id in provider_map:
            if provider_id not in internal_map:
                discrepancies.append({
                    "type": "missing_internal",
                    "provider_id": provider_id,
                    "details": "Payment exists at provider but not internally.",
                })

        report.total_internal = len(internal_map)
        report.total_provider = len(provider_map)
        report.matched_count = (
            len(internal_map) + len(provider_map)
            - len(discrepancies)
            - len(set(internal_map.keys()) ^ set(provider_map.keys()))
        )
        report.matched_count = max(0, min(
            len(internal_map), len(provider_map)
        ) - len(discrepancies))
        report.discrepancy_count = len(discrepancies)
        report.discrepancies = discrepancies  # type: ignore[assignment]
        report.status = "completed"
        report.completed_at = datetime.now(timezone.utc)

    except Exception as exc:
        report.status = "failed"
        report.completed_at = datetime.now(timezone.utc)
        report.discrepancies = {"error": str(exc)}  # type: ignore[assignment]
        await db.flush()
        raise ReconciliationError(str(exc)) from exc

    await db.flush()

    await audit_service.log_action(
        db,
        actor_id=actor_id,
        actor_type="admin" if actor_id != "system" else "system",
        action="reconciliation.completed",
        resource_type="reconciliation_report",
        resource_id=report.id,
        details={
            "total_internal": report.total_internal,
            "total_provider": report.total_provider,
            "discrepancies": report.discrepancy_count,
        },
    )

    return report


async def get_report(
    db: AsyncSession, report_id: object
) -> ReconciliationReport | None:
    stmt = select(ReconciliationReport).where(ReconciliationReport.id == report_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_reports(
    db: AsyncSession, limit: int = 20, offset: int = 0
) -> tuple[list[ReconciliationReport], int]:
    from sqlalchemy import func

    stmt = (
        select(ReconciliationReport)
        .order_by(ReconciliationReport.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count(ReconciliationReport.id))

    result = await db.execute(stmt)
    reports = list(result.scalars().all())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()
    return reports, total
