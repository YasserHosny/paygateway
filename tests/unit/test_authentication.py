import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.config import get_settings
from paygateway.middleware.authentication import (
    AuthenticatedUser,
    _authenticate_api_key,
    _authenticate_jwt,
    require_role,
)
from paygateway.models.api_key import ApiKey


def _make_key() -> tuple[str, str]:
    """Returns (raw_key, prefix) with a guaranteed-unique 8-char prefix."""
    uid = uuid.uuid4().hex  # 32 hex chars, unique each call
    prefix = uid[:8]
    raw = f"{prefix}_{uid[8:]}"
    return raw, prefix


def _hash_key(raw: str) -> str:
    s = get_settings()
    return hashlib.sha256(f"{s.API_KEY_SALT}{raw}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_valid_api_key_returns_authenticated_user(db_session: AsyncSession):
    raw, prefix = _make_key()
    db_session.add(ApiKey(
        name="valid-key",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role="admin",
        is_active=True,
    ))
    await db_session.flush()

    user = await _authenticate_api_key(db_session, raw)

    assert user.role == "admin"
    assert user.auth_type == "api_key"
    assert user.user_id  # non-empty string


@pytest.mark.unit
async def test_valid_api_key_sets_last_used_at(db_session: AsyncSession):
    raw, prefix = _make_key()
    record = ApiKey(
        name="used-key",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role="service",
        is_active=True,
    )
    db_session.add(record)
    await db_session.flush()
    assert record.last_used_at is None

    await _authenticate_api_key(db_session, raw)

    assert record.last_used_at is not None


@pytest.mark.unit
async def test_nonexistent_key_prefix_raises_401(db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await _authenticate_api_key(db_session, "00000000_nonexistentkey12345678")
    assert exc.value.status_code == 401
    assert exc.value.detail["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.unit
async def test_wrong_key_hash_raises_401(db_session: AsyncSession):
    raw, prefix = _make_key()
    db_session.add(ApiKey(
        name="hash-mismatch",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role="admin",
        is_active=True,
    ))
    await db_session.flush()

    # Same prefix (first 8 chars match), different suffix → wrong hash
    wrong_key = f"{prefix}_totally_wrong_suffix_here"
    with pytest.raises(HTTPException) as exc:
        await _authenticate_api_key(db_session, wrong_key)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_expired_api_key_raises_401(db_session: AsyncSession):
    raw, prefix = _make_key()
    db_session.add(ApiKey(
        name="expired-key",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role="admin",
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    ))
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await _authenticate_api_key(db_session, raw)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_inactive_api_key_raises_401(db_session: AsyncSession):
    raw, prefix = _make_key()
    db_session.add(ApiKey(
        name="inactive-key",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role="admin",
        is_active=False,
    ))
    await db_session.flush()

    # Inactive key is filtered by is_active=True query, so it won't be found
    with pytest.raises(HTTPException) as exc:
        await _authenticate_api_key(db_session, raw)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# JWT authentication
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_jwt_returns_user():
    s = get_settings()
    token = jwt.encode(
        {"sub": "user-123", "role": "admin"},
        s.JWT_SECRET_KEY,
        algorithm=s.JWT_ALGORITHM,
    )
    user = _authenticate_jwt(token)
    assert user.user_id == "user-123"
    assert user.role == "admin"
    assert user.auth_type == "jwt"


@pytest.mark.unit
def test_jwt_defaults_role_to_readonly():
    s = get_settings()
    token = jwt.encode({"sub": "user-456"}, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    user = _authenticate_jwt(token)
    assert user.role == "readonly"


@pytest.mark.unit
def test_jwt_missing_sub_raises_401():
    s = get_settings()
    token = jwt.encode({"role": "admin"}, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        _authenticate_jwt(token)
    assert exc.value.status_code == 401


@pytest.mark.unit
def test_jwt_wrong_secret_raises_401():
    token = jwt.encode({"sub": "u1", "role": "admin"}, "wrong-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        _authenticate_jwt(token)
    assert exc.value.status_code == 401


@pytest.mark.unit
def test_jwt_malformed_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        _authenticate_jwt("not.a.valid.token")
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# require_role
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_require_role_allows_matching_role():
    user = AuthenticatedUser(user_id="u1", role="admin", auth_type="api_key")
    result = await require_role("admin", "service")(user=user)
    assert result.role == "admin"


@pytest.mark.unit
async def test_require_role_blocks_insufficient_role():
    user = AuthenticatedUser(user_id="u1", role="readonly", auth_type="api_key")
    with pytest.raises(HTTPException) as exc:
        await require_role("admin")(user=user)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"]["code"] == "FORBIDDEN"


@pytest.mark.unit
async def test_require_role_accepts_any_of_multiple_roles():
    for role in ("admin", "service"):
        user = AuthenticatedUser(user_id="u1", role=role, auth_type="api_key")
        result = await require_role("admin", "service")(user=user)
        assert result.role == role
