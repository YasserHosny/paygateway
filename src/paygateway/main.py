from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from paygateway.config import get_settings
from paygateway.middleware.correlation import CorrelationIdMiddleware
from paygateway.middleware.rate_limiting import RateLimitMiddleware
from paygateway.routes import api_v1_router
from paygateway.routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    if settings.ENVIRONMENT != "development" and not _is_test_run():
        from paygateway.db.session import _get_session_factory
        from paygateway.jobs.scheduler import scheduler
        from paygateway.jobs.cleanup import cleanup_expired_idempotency_records, cleanup_old_webhook_events
        from paygateway.jobs.reconciliation import run_daily_reconciliation

        session_factory = _get_session_factory()
        scheduler.register("cleanup_idempotency", lambda: cleanup_expired_idempotency_records(session_factory), interval_seconds=86400)
        scheduler.register("cleanup_webhooks", lambda: cleanup_old_webhook_events(session_factory), interval_seconds=86400)
        scheduler.register("reconciliation", lambda: run_daily_reconciliation(session_factory), interval_seconds=86400)
        await scheduler.start()
        yield
        await scheduler.stop()
    else:
        yield


def _is_test_run() -> bool:
    import sys
    return "pytest" in sys.modules


app = FastAPI(
    title="Payment Gateway Core Service",
    description="Reusable payment orchestration layer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type", "Authorization", "X-API-Key",
        "Idempotency-Key", "X-Request-ID",
    ],
    expose_headers=[
        "X-Request-ID", "X-RateLimit-Limit",
        "X-RateLimit-Remaining", "X-RateLimit-Reset",
    ],
    max_age=600,
)

app.include_router(health_router)
app.include_router(api_v1_router)
