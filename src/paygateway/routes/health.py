from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.config import get_settings
from paygateway.db.session import get_db
from paygateway.schemas.health import HealthResponse, InfoResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    overall = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"

    return HealthResponse(
        status=overall,
        checks=checks,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/info", response_model=InfoResponse)
async def info() -> InfoResponse:
    return InfoResponse(environment=get_settings().ENVIRONMENT)
