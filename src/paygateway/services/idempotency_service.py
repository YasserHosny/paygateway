import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.idempotency import IdempotencyRecord


class IdempotencyConflictError(Exception):
    pass


async def check_idempotency(
    db: AsyncSession,
    *,
    key: str,
    request_path: str,
    request_method: str,
    request_body: dict,
) -> IdempotencyRecord | None:
    stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == key)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        return None

    expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.delete(record)
        await db.flush()
        return None

    body_hash = _hash_body(request_body)
    if record.request_hash != body_hash:
        raise IdempotencyConflictError(
            "Idempotency key already used with a different request body"
        )

    return record


async def store_idempotency(
    db: AsyncSession,
    *,
    key: str,
    request_path: str,
    request_method: str,
    request_body: dict,
    response_status: int,
    response_body: dict,
    ttl_hours: int = 24,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        key=key,
        request_path=request_path,
        request_method=request_method,
        request_hash=_hash_body(request_body),
        response_status=response_status,
        response_body=response_body,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    db.add(record)
    await db.flush()
    return record


async def cleanup_expired(db: AsyncSession) -> int:
    stmt = delete(IdempotencyRecord).where(
        IdempotencyRecord.expires_at < datetime.now(timezone.utc)
    )
    result = await db.execute(stmt)
    return result.rowcount  # type: ignore[return-value]


def _hash_body(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
