import os

# Must be set before any paygateway imports
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import hashlib
import ssl
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from paygateway.models import ApiKey
from paygateway.providers.base import (
    PaymentProvider,
    ProviderPaymentIntent,
    ProviderRefund,
)


def _build_test_engine():
    from paygateway.config import get_settings

    s = get_settings()
    connect_args: dict = {"statement_cache_size": 0}
    if s.DATABASE_SSL and "asyncpg" in s.DATABASE_URL:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx
    return create_async_engine(
        s.DATABASE_URL,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


_test_engine = None


def _get_test_engine():
    global _test_engine
    if _test_engine is None:
        _test_engine = _build_test_engine()
    return _test_engine


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = _get_test_engine()
    async with engine.connect() as connection:
        await connection.begin()
        async with AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            yield session
        await connection.rollback()


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock(spec=PaymentProvider)
    provider.create_payment_intent.return_value = ProviderPaymentIntent(
        provider_id="pi_test_123",
        status="pending",
        amount=5000,
        currency="USD",
        client_secret="pi_test_123_secret_abc",
    )
    provider.cancel_payment_intent.return_value = ProviderPaymentIntent(
        provider_id="pi_test_123",
        status="canceled",
        amount=5000,
        currency="USD",
    )
    provider.confirm_payment_intent.return_value = ProviderPaymentIntent(
        provider_id="pi_test_123",
        status="succeeded",
        amount=5000,
        currency="USD",
    )
    provider.create_refund.return_value = ProviderRefund(
        provider_id="re_test_123",
        payment_provider_id="pi_test_123",
        amount=5000,
        currency="USD",
        status="pending",
    )
    return provider


TEST_API_KEY = "pgw_test_aBcDeFgHiJkLmNoPqRsTuVwXyZ12"
TEST_API_KEY_PREFIX = TEST_API_KEY[:8]


def _hash_test_key(key: str) -> str:
    from paygateway.config import get_settings

    salted = f"{get_settings().API_KEY_SALT}{key}"
    return hashlib.sha256(salted.encode()).hexdigest()


@pytest.fixture
async def admin_api_key(db_session: AsyncSession) -> str:
    api_key = ApiKey(
        name="test-admin",
        key_hash=_hash_test_key(TEST_API_KEY),
        key_prefix=TEST_API_KEY_PREFIX,
        role="admin",
        is_active=True,
    )
    db_session.add(api_key)
    await db_session.flush()
    return TEST_API_KEY


@pytest.fixture
async def client(
    db_session: AsyncSession, mock_provider: AsyncMock, admin_api_key: str
) -> AsyncGenerator[AsyncClient, None]:
    from paygateway.db.session import get_db
    from paygateway.dependencies import get_provider
    from paygateway.main import app

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_provider] = lambda: mock_provider

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["X-API-Key"] = admin_api_key
        yield c

    app.dependency_overrides.clear()
