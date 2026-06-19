import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from paygateway.dependencies import get_provider
from paygateway.services.reconciliation_service import ReconciliationError, run_reconciliation

logger = logging.getLogger(__name__)


async def run_daily_reconciliation(session_factory: async_sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)

    logger.info("Running scheduled reconciliation for %s to %s", start.date(), end.date())

    provider = get_provider()
    async with session_factory() as db:
        try:
            report = await run_reconciliation(
                db, provider,
                date_range_start=start,
                date_range_end=end,
                actor_id="system",
            )
            await db.commit()
            logger.info(
                "Scheduled reconciliation completed: %d discrepancies across %d internal / %d provider records",
                report.discrepancy_count,
                report.total_internal,
                report.total_provider,
            )
        except ReconciliationError:
            logger.exception("Scheduled reconciliation failed")
