"""
Integration tests for authentication and role-based access control.
Verifies that each role (admin / service / readonly) can access exactly
what it is permitted to access, and that JWT Bearer tokens are accepted.
"""
import hashlib
import uuid

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.config import get_settings
from paygateway.models.api_key import ApiKey


def _make_key() -> tuple[str, str]:
    """Return (raw_key, prefix) with a unique 8-char prefix."""
    uid = uuid.uuid4().hex
    prefix = uid[:8]
    raw = f"{prefix}_{uid[8:]}"
    return raw, prefix


def _hash_key(raw: str) -> str:
    s = get_settings()
    return hashlib.sha256(f"{s.API_KEY_SALT}{raw}".encode()).hexdigest()


async def _insert_key(db_session: AsyncSession, role: str) -> str:
    raw, prefix = _make_key()
    db_session.add(ApiKey(
        name=f"rbac-test-{role}",
        key_hash=_hash_key(raw),
        key_prefix=prefix,
        role=role,
        is_active=True,
    ))
    await db_session.flush()
    return raw


# ---------------------------------------------------------------------------
# readonly role
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_readonly_can_list_payments(client: AsyncClient, db_session: AsyncSession):
    readonly_key = await _insert_key(db_session, "readonly")
    client.headers["X-API-Key"] = readonly_key

    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 200


@pytest.mark.integration
async def test_readonly_cannot_create_payment(client: AsyncClient, db_session: AsyncSession):
    readonly_key = await _insert_key(db_session, "readonly")
    client.headers["X-API-Key"] = readonly_key

    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


@pytest.mark.integration
async def test_readonly_cannot_create_refund(client: AsyncClient, db_session: AsyncSession):
    readonly_key = await _insert_key(db_session, "readonly")
    client.headers["X-API-Key"] = readonly_key

    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# service role
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_service_can_create_payment(client: AsyncClient, db_session: AsyncSession):
    service_key = await _insert_key(db_session, "service")
    client.headers["X-API-Key"] = service_key

    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201


@pytest.mark.integration
async def test_service_cannot_create_refund(client: AsyncClient, db_session: AsyncSession):
    """Refund endpoint requires admin; service role must be rejected."""
    service_key = await _insert_key(db_session, "service")
    client.headers["X-API-Key"] = service_key

    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


@pytest.mark.integration
async def test_service_cannot_run_reconciliation(client: AsyncClient, db_session: AsyncSession):
    service_key = await _insert_key(db_session, "service")
    client.headers["X-API-Key"] = service_key

    resp = await client.post(
        "/api/v1/admin/reconciliation/run",
        json={
            "date_range_start": "2024-01-01T00:00:00Z",
            "date_range_end": "2024-01-02T00:00:00Z",
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# JWT Bearer auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_jwt_bearer_token_accepted(client: AsyncClient):
    s = get_settings()
    token = jwt.encode(
        {"sub": "jwt-user-1", "role": "admin"},
        s.JWT_SECRET_KEY,
        algorithm=s.JWT_ALGORITHM,
    )
    # Send with empty API key (falsy) so auth falls through to JWT path
    resp = await client.get(
        "/api/v1/payments",
        headers={"X-API-Key": "", "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.integration
async def test_jwt_with_readonly_role_cannot_create(client: AsyncClient):
    s = get_settings()
    token = jwt.encode(
        {"sub": "jwt-readonly", "role": "readonly"},
        s.JWT_SECRET_KEY,
        algorithm=s.JWT_ALGORITHM,
    )
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={
            "X-API-Key": "",
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 403


@pytest.mark.integration
async def test_invalid_jwt_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/payments",
        headers={"X-API-Key": "", "Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.integration
async def test_no_credentials_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/payments",
        headers={"X-API-Key": ""},
    )
    assert resp.status_code == 401
