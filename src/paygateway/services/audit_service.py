import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.models.audit_log import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    actor_id: str,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    outcome: str = "success",
) -> AuditLog:
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        outcome=outcome,
    )
    db.add(entry)
    await db.flush()
    return entry
