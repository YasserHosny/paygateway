# Testing Guide

## Test Suite Overview

```
tests/
├── unit/                   # Pure logic, no DB or network
│   ├── test_authentication.py
│   ├── test_rate_limiting.py
│   ├── test_payment_service.py
│   ├── test_refund_service.py
│   ├── test_stripe_provider.py
│   ├── test_idempotency_service.py
│   ├── test_reconciliation_service.py
│   ├── test_webhook_service.py
│   └── test_validation.py
├── integration/            # Full HTTP stack against test DB
│   ├── test_payment_api.py
│   ├── test_refund_api.py
│   ├── test_health_api.py
│   ├── test_auth_rbac_api.py
│   ├── test_rate_limit_api.py
│   ├── test_idempotency_api.py
│   ├── test_webhook_api.py
│   └── test_reconciliation_api.py
└── e2e/                    # Full lifecycle flows
    ├── test_payment_flow.py
    ├── test_refund_flow.py
    └── test_error_scenarios.py
```

---

## Running Tests

### All tests

```bash
pytest
```

### With coverage report

```bash
pytest --cov=paygateway --cov-report=html
open htmlcov/index.html
```

### Unit tests only (fast, no DB)

```bash
pytest tests/unit/
```

### Integration tests only

```bash
pytest tests/integration/
```

### Specific file

```bash
pytest tests/unit/test_payment_service.py -v
```

### Run with verbose output

```bash
pytest -v --tb=short
```

---

## Test Configuration (`conftest.py`)

The test suite uses:
- **Real Supabase DB** — integration and e2e tests hit the actual database
- **Mocked Stripe** — Stripe API calls are mocked in unit tests; integration tests use real Stripe test mode
- **`AsyncClient`** from `httpx` — for HTTP-level integration testing

Key fixtures:

| Fixture | Scope | Description |
|---------|-------|-------------|
| `engine` | session | Async SQLAlchemy engine connected to test DB |
| `db` | function | Async DB session, rolled back after each test |
| `client` | function | `AsyncClient` with FastAPI test app |
| `admin_api_key` | function | Creates a test admin API key in DB |
| `readonly_api_key` | function | Creates a test readonly API key |

---

## Safe Stripe Testing

PayGateway uses **Stripe test mode** — no real money moves.

### Test API Keys

Use keys starting with `sk_test_` and `pk_test_` in your `.env` for testing.

### Test Payment Methods

Stripe provides magic payment method IDs for server-side confirms (no card number needed):

| ID | Behavior |
|----|---------|
| `pm_card_visa` | Always succeeds |
| `pm_card_mastercard` | Always succeeds |
| `pm_card_visa_debit` | Always succeeds |
| `pm_card_chargeDeclined` | Declined — `card_declined` |
| `pm_card_cvcCheckFail` | Declined — `incorrect_cvc` |
| `pm_card_insufficientFunds` | Declined — `insufficient_funds` |
| `pm_card_expiredCard` | Declined — `expired_card` |

### Test Card Numbers (for Stripe.js on the frontend)

| Number | Behavior |
|--------|---------|
| `4242 4242 4242 4242` | Visa — always succeeds |
| `4000 0025 0000 3155` | Requires 3DS authentication |
| `4000 0000 0000 9995` | Always declined — insufficient funds |
| `4000 0000 0000 0002` | Always declined |

Use expiry `12/34`, CVV `123`, ZIP `10001` for any test card.

---

## Live Lifecycle Validation (Chrome DevTools / curl)

This is the manual smoke test used to validate the full flow:

```javascript
// Run in browser console against http://127.0.0.1:8765/docs
const BASE = "http://127.0.0.1:8765";
const API_KEY = "your-test-api-key";
const ts = Date.now();

const req = async (method, path, body, ikey) => {
  const hdrs = { "Content-Type": "application/json", "X-API-Key": API_KEY };
  if (ikey) hdrs["Idempotency-Key"] = ikey;
  const r = await fetch(BASE + path, { method, headers: hdrs, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, data: await r.json() };
};

// 1. Create
const { data: payment } = await req("POST", "/api/v1/payments",
  { amount: 2500, currency: "usd", metadata: { test: "true" } }, `cp-${ts}`);

// 2. Confirm
await req("POST", `/api/v1/payments/${payment.id}/confirm`,
  { payment_method_id: "pm_card_visa" }, `cf-${ts}`);

// 3. Refund
await req("POST", `/api/v1/payments/${payment.id}/refund`,
  { amount: 1000, reason: "customer_request" }, `ref-${ts}`);
```

### Expected results

| Step | Expected HTTP |
|------|--------------|
| Create | `201` — status `pending` |
| Confirm | `200` — status `succeeded` |
| Get | `200` — status `succeeded` |
| Refund | `201` — status `succeeded` |
| Get refund | `200` — status `succeeded` |
| Cancel fresh payment | `200` — status `canceled` |
| Replay same idempotency key | `201` — same `id` as original |

---

## Webhook Testing

Use Stripe CLI to forward events locally:

```bash
stripe listen --forward-to http://127.0.0.1:8765/api/v1/webhooks/stripe
```

Trigger a test event:

```bash
stripe trigger payment_intent.succeeded
```

Or construct a manual test via curl (signature will fail — use Stripe CLI for valid signatures):

```bash
curl -X POST http://127.0.0.1:8765/api/v1/webhooks/stripe \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: t=...,v1=..." \
  -d '{"type":"payment_intent.succeeded","data":{"object":{...}}}'
```

---

## Writing New Tests

### Unit test pattern

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from paygateway.services.payment_service import create_payment

@pytest.mark.asyncio
async def test_create_payment_calls_provider():
    db = AsyncMock()
    provider = AsyncMock()
    provider.create_payment_intent.return_value = MagicMock(
        provider_id="pi_test", status="pending", amount=1000,
        currency="USD", client_secret="secret", metadata={},
        created_at=...,
    )
    # ... assert behaviour
```

### Integration test pattern

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_payment_returns_201(client: AsyncClient, admin_api_key: str):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": 1000, "currency": "USD", "metadata": {}},
        headers={"X-API-Key": admin_api_key, "Idempotency-Key": "test-key-001"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
```

---

## CI Notes

- Tests require `DATABASE_URL` pointing to a test DB (Supabase works fine)
- Set `ENVIRONMENT=development` to disable background scheduler
- Stripe calls in integration tests use real test-mode keys — no mocking needed
- All tests are idempotent: unique `Idempotency-Key` values prevent conflicts across runs
