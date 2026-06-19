import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.services.idempotency_service import (
    IdempotencyConflictError,
    check_idempotency,
    cleanup_expired,
    store_idempotency,
)


@pytest.mark.unit
async def test_new_key_returns_none(db_session: AsyncSession):
    result = await check_idempotency(
        db_session, key="new-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
    )
    assert result is None


@pytest.mark.unit
async def test_duplicate_key_returns_cached(db_session: AsyncSession):
    await store_idempotency(
        db_session, key="dup-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
        response_status=201, response_body={"id": "abc"},
    )
    await db_session.commit()

    result = await check_idempotency(
        db_session, key="dup-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
    )
    assert result is not None
    assert result.response_status == 201
    assert result.response_body == {"id": "abc"}


@pytest.mark.unit
async def test_key_mismatch_body_raises(db_session: AsyncSession):
    await store_idempotency(
        db_session, key="mismatch-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
        response_status=201, response_body={"id": "abc"},
    )
    await db_session.commit()

    with pytest.raises(IdempotencyConflictError):
        await check_idempotency(
            db_session, key="mismatch-key", request_path="/test",
            request_method="POST", request_body={"amount": 999},
        )


@pytest.mark.unit
async def test_expired_key_returns_none(db_session: AsyncSession):
    await store_idempotency(
        db_session, key="expired-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
        response_status=201, response_body={"id": "abc"},
        ttl_hours=-1,
    )
    await db_session.commit()

    result = await check_idempotency(
        db_session, key="expired-key", request_path="/test",
        request_method="POST", request_body={"amount": 100},
    )
    assert result is None
