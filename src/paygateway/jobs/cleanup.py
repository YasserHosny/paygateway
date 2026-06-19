import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from paygateway.models.idempotency import IdempotencyRecord
from paygateway.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)

WEBHOOK_RETENTION_DAYS = 90


async def cleanup_expired_idempotency_records(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        stmt = delete(IdempotencyRecord).where(
            IdempotencyRecord.expires_at < datetime.now(timezone.utc)
        )
        result = await db.execute(stmt)
        await db.commit()
        count = result.rowcount
        if count:
            logger.info("Deleted %d expired idempotency records", count)


async def cleanup_old_webhook_events(session_factory: async_sessionmaker) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WEBHOOK_RETENTION_DAYS)
    async with session_factory() as db:
        stmt = delete(WebhookEvent).where(
            WebhookEvent.processed.is_(True),
            WebhookEvent.created_at < cutoff,
        )
        result = await db.execute(stmt)
        await db.commit()
        count = result.rowcount
        if count:
            logger.info("Archived %d old webhook events older than %d days", count, WEBHOOK_RETENTION_DAYS)
