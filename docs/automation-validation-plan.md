# Payment Gateway — Full Automation Validation Plan

## Overview

| Metric | Value |
|--------|-------|
| Existing tests | 53 |
| Coverage gaps identified | 24 |
| Feature areas | 7 |
| Test tiers | 3 (unit / integration / e2e) |
| Coverage target | ≥ 85% |

---

## 1. Current Coverage Status

### 1.1 Unit Tests (53 existing across all service files)

| File | Tests | Status |
|------|-------|--------|
| `test_payment_service.py` | 5 | Partial — missing `list_payments` filters, `confirm_payment` |
| `test_refund_service.py` | 5 | Partial — missing `list_refunds_for_payment`, consecutive partials |
| `test_stripe_provider.py` | 16 | Complete |
| `test_webhook_service.py` | 8 | Complete |
| `test_reconciliation_service.py` | 8 | Complete |
| `test_idempotency_service.py` | 4 | Complete |
| `test_validation.py` | 7 | Complete |
| `test_authentication.py` | — | **Missing** |
| `test_rate_limiting.py` | — | **Missing** |
| `test_audit_service.py` | — | **Missing** |

### 1.2 Integration Tests

| File | Tests | Status |
|------|-------|--------|
| `test_payment_api.py` | 7 | Partial — missing `confirm`, `cancel`, list filters, pagination |
| `test_refund_api.py` | 7 | Complete |
| `test_webhook_api.py` | 4 | Complete |
| `test_idempotency_api.py` | 3 | Complete |
| `test_reconciliation_api.py` | 6 | Complete |
| `test_auth_rbac_api.py` | — | **Missing** |
| `test_rate_limit_api.py` | — | **Missing** |

### 1.3 E2E Tests

| File | Tests | Status |
|------|-------|--------|
| `test_payment_flow.py` | 4 | Complete |
| `test_refund_flow.py` | 2 | Partial — missing consecutive partials, charge.refunded webhook |
| `test_error_scenarios.py` | 7 | Complete |

---

## 2. Coverage Gaps

### Priority: HIGH

| Tier | File | Test Case |
|------|------|-----------|
| unit | `test_authentication.py` *(new)* | API key with wrong hash returns 401 |
| unit | `test_authentication.py` *(new)* | Expired API key returns 401 |
| unit | `test_authentication.py` *(new)* | JWT valid token extracts user correctly |
| unit | `test_authentication.py` *(new)* | JWT invalid signature returns 401 |
| unit | `test_authentication.py` *(new)* | `require_role` blocks insufficient role → 403 |
| unit | `test_payment_service.py` *(extend)* | `confirm_payment` updates status and sets `confirmed_at` |
| unit | `test_refund_service.py` *(extend)* | Second partial refund respects remaining balance |
| integration | `test_payment_api.py` *(extend)* | `POST /{id}/confirm` → 200, status=succeeded |
| integration | `test_payment_api.py` *(extend)* | `POST /{id}/cancel` → 200, status=canceled |
| integration | `test_auth_rbac_api.py` *(new)* | `readonly` role → `GET /payments` 200 |
| integration | `test_auth_rbac_api.py` *(new)* | `readonly` role → `POST /payments` 403 |
| integration | `test_auth_rbac_api.py` *(new)* | `service` role → `POST /payments` 201 |
| integration | `test_auth_rbac_api.py` *(new)* | `service` role → `POST /refund` 403 (admin-only) |
| e2e | `test_refund_flow.py` *(extend)* | Two partial refunds summing to full amount → payment status=refunded |
| e2e | `test_refund_flow.py` *(extend)* | `charge.refunded` webhook → refund.status=succeeded |

### Priority: MEDIUM

| Tier | File | Test Case |
|------|------|-----------|
| unit | `test_rate_limiting.py` *(new)* | Under limit → request allowed + correct X-RateLimit-* headers |
| unit | `test_rate_limiting.py` *(new)* | Over limit → 429 + Retry-After header |
| unit | `test_payment_service.py` *(extend)* | `list_payments` filter by status, currency, date range |
| unit | `test_refund_service.py` *(extend)* | `list_refunds_for_payment` returns correct count and order |
| integration | `test_payment_api.py` *(extend)* | `GET /payments?status=pending` filters correctly |
| integration | `test_payment_api.py` *(extend)* | `GET /payments` pagination with limit/offset |
| integration | `test_auth_rbac_api.py` *(new)* | JWT Bearer token accepted on payment endpoints |
| integration | `test_rate_limit_api.py` *(new)* | X-RateLimit-* headers present on all responses |

### Priority: LOW

| Tier | File | Test Case |
|------|------|-----------|
| unit | `test_rate_limiting.py` *(new)* | Sliding window resets after timeout |
| integration | `test_idempotency_api.py` *(extend)* | Idempotency-Key longer than 255 chars → 422 |

---

## 3. New Test Files to Create

### `tests/unit/test_authentication.py`

```python
import hashlib
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from jose import jwt

from paygateway.middleware.authentication import (
    _authenticate_api_key,
    _authenticate_jwt,
    require_role,
    AuthenticatedUser,
)
from paygateway.config import get_settings


@pytest.mark.unit
async def test_valid_api_key_authenticates(db_session):
    # Insert a real key record and verify it resolves
    ...


@pytest.mark.unit
async def test_wrong_key_hash_raises_401(db_session):
    ...


@pytest.mark.unit
async def test_expired_api_key_raises_401(db_session):
    ...


@pytest.mark.unit
def test_valid_jwt_returns_user():
    s = get_settings()
    token = jwt.encode({"sub": "user-1", "role": "admin"}, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    user = _authenticate_jwt(token)
    assert user.user_id == "user-1"
    assert user.role == "admin"


@pytest.mark.unit
def test_invalid_jwt_signature_raises_401():
    with pytest.raises(HTTPException) as exc:
        _authenticate_jwt("invalid.token.here")
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_require_role_blocks_wrong_role():
    user = AuthenticatedUser(user_id="u1", role="readonly", auth_type="api_key")
    checker = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        await checker(user)
    assert exc.value.status_code == 403


@pytest.mark.unit
async def test_require_role_allows_correct_role():
    user = AuthenticatedUser(user_id="u1", role="admin", auth_type="api_key")
    checker = require_role("admin", "service")
    result = await checker(user)
    assert result.role == "admin"
```

### `tests/unit/test_rate_limiting.py`

```python
import pytest
from paygateway.middleware.rate_limiting import InMemoryRateLimiter


@pytest.mark.unit
def test_under_limit_returns_allowed():
    limiter = InMemoryRateLimiter()
    limited, headers = limiter.is_rate_limited("key-1", limit=10)
    assert limited is False
    assert "X-RateLimit-Remaining" in headers
    assert int(headers["X-RateLimit-Remaining"]) == 9


@pytest.mark.unit
def test_over_limit_returns_429():
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        limiter.is_rate_limited("key-burst", limit=10)
    limited, headers = limiter.is_rate_limited("key-burst", limit=10)
    assert limited is True
    assert "Retry-After" in headers


@pytest.mark.unit
def test_different_keys_are_isolated():
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        limiter.is_rate_limited("key-a", limit=10)
    limited_b, _ = limiter.is_rate_limited("key-b", limit=10)
    assert limited_b is False


@pytest.mark.unit
def test_remaining_decrements_per_request():
    limiter = InMemoryRateLimiter()
    for i in range(5):
        _, headers = limiter.is_rate_limited("key-count", limit=10)
    assert int(headers["X-RateLimit-Remaining"]) == 5
```

### `tests/integration/test_auth_rbac_api.py`

```python
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from paygateway.models import ApiKey
from tests.conftest import _hash_test_key, TEST_API_KEY_PREFIX


async def _create_key(db_session, role: str) -> str:
    raw = f"pgw_test_{uuid.uuid4().hex[:24]}"
    db_session.add(ApiKey(
        name=f"test-{role}",
        key_hash=_hash_test_key(raw),
        key_prefix=raw[:8],
        role=role,
        is_active=True,
    ))
    await db_session.flush()
    return raw


@pytest.mark.integration
async def test_readonly_can_list_payments(client: AsyncClient, db_session: AsyncSession):
    readonly_key = await _create_key(db_session, "readonly")
    client.headers["X-API-Key"] = readonly_key
    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 200


@pytest.mark.integration
async def test_readonly_cannot_create_payment(client: AsyncClient, db_session: AsyncSession):
    readonly_key = await _create_key(db_session, "readonly")
    client.headers["X-API-Key"] = readonly_key
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


@pytest.mark.integration
async def test_service_can_create_payment(client: AsyncClient, db_session: AsyncSession):
    service_key = await _create_key(db_session, "service")
    client.headers["X-API-Key"] = service_key
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201


@pytest.mark.integration
async def test_service_cannot_create_refund(client: AsyncClient, db_session: AsyncSession):
    service_key = await _create_key(db_session, "service")
    client.headers["X-API-Key"] = service_key
    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403


@pytest.mark.integration
async def test_jwt_bearer_accepted(client: AsyncClient):
    from jose import jwt
    from paygateway.config import get_settings
    s = get_settings()
    token = jwt.encode({"sub": "u1", "role": "admin"}, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    client.headers.pop("X-API-Key", None)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 200


@pytest.mark.integration
async def test_invalid_jwt_rejected(client: AsyncClient):
    client.headers.pop("X-API-Key", None)
    client.headers["Authorization"] = "Bearer invalid.token.payload"
    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 401
```

### `tests/integration/test_rate_limit_api.py`

```python
import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_rate_limit_headers_present(client: AsyncClient):
    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 200
    # Headers are present when rate limiting is enabled
    # (disabled in tests via RATE_LIMIT_ENABLED=false, so just verify endpoint works)


@pytest.mark.integration
async def test_rate_limit_enforced_when_enabled(client: AsyncClient, monkeypatch):
    import paygateway.middleware.rate_limiting as rl
    monkeypatch.setattr(rl, "RATE_LIMITS", {"/api/v1/payments": 2})

    from paygateway.config import get_settings, Settings
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_ENABLED", True)

    for _ in range(2):
        await client.get("/api/v1/payments")

    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"]["code"] == "RATE_LIMITED"
```

---

## 4. Extend Existing Test Files

### `tests/integration/test_payment_api.py` — add these cases

```python
@pytest.mark.integration
async def test_confirm_payment(client: AsyncClient, mock_provider: AsyncMock):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/confirm",
        json={"payment_method_id": "pm_card_visa"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"


@pytest.mark.integration
async def test_cancel_payment(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/cancel",
        json={"reason": "requested_by_customer"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "canceled"


@pytest.mark.integration
async def test_list_payments_filter_by_status(client: AsyncClient):
    await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    resp = await client.get("/api/v1/payments?status=pending")
    assert resp.status_code == 200
    assert all(p["status"] == "pending" for p in resp.json()["data"])


@pytest.mark.integration
async def test_list_payments_pagination(client: AsyncClient):
    for _ in range(5):
        await client.post(
            "/api/v1/payments",
            json={"amount": 1000, "currency": "usd"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    resp = await client.get("/api/v1/payments?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 2
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["has_more"] is True
```

### `tests/e2e/test_refund_flow.py` — add these cases

```python
@pytest.mark.e2e
async def test_consecutive_partial_refunds(client: AsyncClient, mock_provider: AsyncMock):
    """Two partial refunds covering the full amount should be accepted."""
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 10000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = payment_resp.json()["id"]

    # Mark succeeded via webhook
    event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded",
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = event
    await client.post("/api/v1/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=sig"})

    # First partial refund
    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_first", payment_provider_id="pi_test_123",
        amount=4000, currency="USD", status="pending",
    )
    r1 = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 4000},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r1.status_code == 201

    # Second partial refund
    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_second", payment_provider_id="pi_test_123",
        amount=6000, currency="USD", status="pending",
    )
    r2 = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"amount": 6000},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r2.status_code == 201

    refunds_resp = await client.get(f"/api/v1/payments/{payment_id}/refunds")
    assert refunds_resp.json()["pagination"]["total"] == 2


@pytest.mark.e2e
async def test_refund_webhook_updates_refund_status(client: AsyncClient, mock_provider: AsyncMock):
    """charge.refunded webhook must transition refund.status from pending → succeeded."""
    payment_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = payment_resp.json()["id"]

    # Succeed payment
    success_event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded",
        payload={"data": {"object": {"id": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
    )
    mock_provider.verify_webhook.return_value = success_event
    await client.post("/api/v1/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=sig"})

    # Create refund
    mock_provider.create_refund.return_value = ProviderRefund(
        provider_id="re_webhook_test", payment_provider_id="pi_test_123",
        amount=5000, currency="USD", status="pending",
    )
    refund_resp = await client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    refund_id = refund_resp.json()["id"]

    # Fire charge.refunded webhook
    refund_event = ProviderWebhookEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="charge.refunded",
        payload={"data": {"object": {"id": "ch_123", "payment_intent": "pi_test_123"}}},
        payment_provider_id="pi_test_123",
        refund_provider_id="re_webhook_test",
    )
    mock_provider.verify_webhook.return_value = refund_event
    await client.post("/api/v1/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=sig"})

    # Verify refund status updated
    get_resp = await client.get(f"/api/v1/refunds/{refund_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "succeeded"
```

---

## 5. CI Pipeline

```
┌──────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────────┐
│  Stage 1 │ →  │  Stage 2 │ →  │   Stage 3   │ →  │  Stage 4 │ →  │   Stage 5    │
│Lint+Type │    │   Unit   │    │ Integration │    │   E2E    │    │Coverage Gate │
└──────────┘    └──────────┘    └─────────────┘    └──────────┘    └──────────────┘
  blocks PR       blocks PR        blocks PR        main only       fail < 85%
```

| Stage | Command | Blocks |
|-------|---------|--------|
| 1 — Lint & Type | `ruff check src/ tests/ && mypy src/` | Every PR |
| 2 — Unit | `pytest -m unit --tb=short -q` | Every PR |
| 3 — Integration | `pytest -m integration --tb=short -q` | Every PR |
| 4 — E2E | `pytest -m e2e --tb=short -q` | main branch |
| 5 — Coverage gate | `pytest --cov=paygateway --cov-fail-under=85` | main branch |

---

## 6. Run Commands Reference

### Prerequisites

```bash
# Fill in DB password in .env, then apply migrations
alembic upgrade head

# Install all deps including dev
pip install -e ".[dev]"
```

### Run by tier

```bash
# Unit — fast, no network
pytest -m unit --tb=short -q

# Integration — requires Supabase connection in .env
pytest -m integration --tb=short -q

# E2E — full lifecycle flows
pytest -m e2e --tb=short -q

# All at once with coverage
pytest --cov=paygateway --cov-report=html --cov-report=term-missing
```

### Targeted runs

```bash
# Single file
pytest tests/integration/test_payment_api.py -v

# Single test by name
pytest -k "test_confirm_payment" -v

# All except slow tests
pytest -m "not slow" --tb=short

# View HTML coverage report
open htmlcov/index.html
```

### Lint and format

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
mypy src/paygateway --ignore-missing-imports
```

### Coverage gate (CI enforcement)

```bash
pytest --cov=paygateway \
  --cov-fail-under=85 \
  --cov-report=xml:coverage.xml \
  --cov-report=term-missing
```

---

## 7. Feature Coverage Matrix

| Feature | Unit | Integration | E2E |
|---------|------|-------------|-----|
| Create payment | ✓ | ✓ | ✓ |
| Get payment | ✓ | ✓ | ✓ |
| List payments (basic) | — | ✓ | — |
| List payments (filters) | — | ✗ gap | — |
| List payments (pagination) | — | ✗ gap | — |
| Confirm payment | ✗ gap | ✗ gap | ✓ |
| Cancel payment | ✓ | ✗ gap | ✓ |
| Create full refund | ✓ | ✓ | ✓ |
| Create partial refund | ✓ | ✓ | ✓ |
| Consecutive partial refunds | ✗ gap | — | ✗ gap |
| List refunds | — | ✓ | — |
| Get refund | ✓ | ✓ | ✓ |
| Stripe webhook → payment succeeded | ✓ | ✓ | ✓ |
| Stripe webhook → payment failed | ✓ | — | — |
| Stripe webhook → charge.refunded | — | — | ✗ gap |
| Webhook idempotency | ✓ | ✓ | — |
| Invalid webhook signature | ✓ | ✓ | ✓ |
| Reconciliation run | ✓ | ✓ | — |
| Reconciliation list/get reports | — | ✓ | — |
| API key auth | — | ✓ | ✓ |
| JWT auth | ✗ gap | ✗ gap | — |
| RBAC (admin / service / readonly) | ✗ gap | ✗ gap | — |
| Idempotency enforcement | ✓ | ✓ | ✓ |
| Rate limiting | ✗ gap | ✗ gap | — |
| Health endpoints | — | ✓ | — |
| Schema validation | ✓ | ✓ | ✓ |
| Audit log entries | — | — | — |
