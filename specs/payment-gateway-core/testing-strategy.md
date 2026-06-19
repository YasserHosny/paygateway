# Payment Gateway Core Service — Testing Strategy

## 1. Overview

The testing strategy covers unit, integration, and end-to-end tests. The goal is high confidence in correctness, security, and reliability of payment operations.

### Test Pyramid

```
        /  E2E Tests  \          (few, slow, high value)
       /  Integration   \        (moderate count, medium speed)
      /   Unit Tests      \      (many, fast, foundational)
```

## 2. Tools and Configuration

| Tool | Purpose |
|------|---------|
| pytest | Test runner |
| pytest-asyncio | Async test support |
| pytest-cov | Coverage reporting |
| httpx | AsyncClient for API testing |
| factory_boy | Test data factories |
| unittest.mock / pytest-mock | Mocking |
| Stripe test mode | Real Stripe integration tests |
| Stripe CLI | Local webhook testing |
| Docker | Test database (PostgreSQL) |

### pytest Configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests (no external dependencies)",
    "integration: Integration tests (requires database)",
    "e2e: End-to-end tests (requires database + Stripe test mode)",
    "slow: Slow tests (reconciliation, large data sets)",
]
filterwarnings = ["ignore::DeprecationWarning"]
```

## 3. Test Directory Structure

```
tests/
  __init__.py
  conftest.py                  # Shared fixtures (db, client, factories)
  factories.py                 # factory_boy factories
  unit/
    __init__.py
    test_payment_service.py
    test_refund_service.py
    test_webhook_service.py
    test_reconciliation_service.py
    test_idempotency_service.py
    test_audit_service.py
    test_stripe_provider.py    # Mocked Stripe SDK
    test_authentication.py
    test_rate_limiting.py
    test_validation.py
  integration/
    __init__.py
    test_payment_api.py
    test_refund_api.py
    test_webhook_api.py
    test_reconciliation_api.py
    test_idempotency_api.py
    test_health_api.py
    test_database.py
    test_migrations.py
  e2e/
    __init__.py
    test_payment_flow.py       # Full payment lifecycle
    test_refund_flow.py        # Full refund lifecycle
    test_error_scenarios.py    # Error and edge cases
```

## 4. Shared Fixtures (conftest.py)

### Database Fixture

```python
@pytest.fixture
async def db_session():
    """Provide a transactional database session that rolls back after each test."""
    # Create test database tables
    # Yield session within a transaction
    # Rollback after test
```

### API Client Fixture

```python
@pytest.fixture
async def client(db_session):
    """Provide an httpx AsyncClient pointing at the test app."""
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
```

### Authenticated Client Fixture

```python
@pytest.fixture
async def admin_client(client, db_session):
    """Client with admin API key."""
    # Create test API key with admin role
    # Return client with X-API-Key header set

@pytest.fixture
async def service_client(client, db_session):
    """Client with service API key."""
    # Create test API key with service role
```

### Mock Provider Fixture

```python
@pytest.fixture
def mock_provider():
    """Provide a mock PaymentProvider for unit tests."""
    provider = AsyncMock(spec=PaymentProvider)
    provider.create_payment_intent.return_value = ProviderPaymentIntent(...)
    return provider
```

## 5. Unit Tests

### 5.1 Payment Service

| Test Case | Description |
|-----------|-------------|
| test_create_payment_success | Creates payment, calls provider, stores record |
| test_create_payment_invalid_amount | Rejects zero or negative amount |
| test_create_payment_invalid_currency | Rejects invalid currency code |
| test_create_payment_provider_error | Handles provider failure gracefully |
| test_get_payment_found | Returns payment by ID |
| test_get_payment_not_found | Returns 404 for nonexistent ID |
| test_list_payments_with_filters | Filters by status, customer, date |
| test_cancel_payment_success | Cancels pending payment |
| test_cancel_payment_already_succeeded | Rejects cancel on succeeded payment |

### 5.2 Refund Service

| Test Case | Description |
|-----------|-------------|
| test_create_full_refund | Full refund of succeeded payment |
| test_create_partial_refund | Partial refund with valid amount |
| test_refund_exceeds_amount | Rejects refund exceeding remaining amount |
| test_refund_non_refundable_status | Rejects refund on pending/failed/canceled payment |
| test_multiple_partial_refunds | Multiple refunds up to original amount |

### 5.3 Webhook Service

| Test Case | Description |
|-----------|-------------|
| test_process_payment_succeeded | Updates payment status to succeeded |
| test_process_payment_failed | Updates payment status to failed with error details |
| test_duplicate_event_ignored | Same event ID processed only once |
| test_unknown_event_type_acknowledged | Unknown events return success, logged |
| test_invalid_state_transition | Does not overwrite refunded with succeeded |
| test_orphan_event_handled | Event for unknown payment logged, not errored |

### 5.4 Idempotency Service

| Test Case | Description |
|-----------|-------------|
| test_new_key_proceeds | New idempotency key allows processing |
| test_duplicate_key_returns_cached | Same key + same body returns cached response |
| test_key_mismatch_body_rejected | Same key + different body returns 422 |
| test_expired_key_allows_reuse | Expired key treated as new |
| test_concurrent_duplicate_keys | Only one request processed |

### 5.5 Stripe Provider (Mocked)

| Test Case | Description |
|-----------|-------------|
| test_create_intent_maps_correctly | Stripe response mapped to ProviderPaymentIntent |
| test_status_mapping | All Stripe statuses map to normalized statuses |
| test_error_mapping | Stripe exceptions map to ProviderError hierarchy |
| test_webhook_verification_valid | Valid signature accepted |
| test_webhook_verification_invalid | Invalid signature raises error |

## 6. Integration Tests

### 6.1 Payment API

| Test Case | Description |
|-----------|-------------|
| test_create_payment_endpoint | POST /payments returns 201 with payment data |
| test_create_payment_unauthenticated | Returns 401 without API key |
| test_create_payment_unauthorized_role | Readonly role returns 403 |
| test_get_payment_endpoint | GET /payments/{id} returns payment |
| test_list_payments_pagination | Pagination works correctly |
| test_idempotency_enforcement | Duplicate POST returns same response |

### 6.2 Webhook API

| Test Case | Description |
|-----------|-------------|
| test_webhook_valid_signature | Verified event processed, returns 200 |
| test_webhook_invalid_signature | Returns 400 |
| test_webhook_duplicate_event | Returns 200, not reprocessed |
| test_webhook_updates_payment | Payment status updated after webhook |

### 6.3 Database

| Test Case | Description |
|-----------|-------------|
| test_migration_up | All migrations apply cleanly |
| test_migration_down | All migrations reverse cleanly |
| test_unique_constraints | Idempotency key uniqueness enforced |
| test_foreign_keys | Refund FK to payment enforced |

## 7. End-to-End Tests

These tests use Stripe test mode with real API calls.

### 7.1 Payment Lifecycle

```
1. Create payment (POST /payments) → get client_secret
2. Confirm via Stripe API (simulate client-side confirmation using test card)
3. Receive webhook (payment_intent.succeeded) via simulated event
4. Verify payment status = succeeded (GET /payments/{id})
5. Verify audit log has creation and confirmation entries
```

### 7.2 Refund Lifecycle

```
1. Create and confirm payment (steps 1-3 above)
2. Create partial refund (POST /payments/{id}/refund)
3. Receive webhook (charge.refunded)
4. Verify refund status = succeeded
5. Verify payment status = partially_refunded
6. Create another refund for remaining amount
7. Verify payment status = refunded
```

### 7.3 Error Scenarios

```
1. Create payment with declined test card → verify status = failed
2. Create payment and cancel → verify status = canceled
3. Attempt refund on pending payment → verify 409 error
4. Attempt refund exceeding amount → verify 409 error
5. Send webhook with invalid signature → verify 400
```

## 8. Coverage Targets

| Area | Target |
|------|--------|
| Service layer | >= 90% |
| Routes | >= 85% |
| Provider adapter | >= 85% |
| Middleware | >= 80% |
| Overall | >= 85% |

## 9. CI Integration

```yaml
# Run on every PR
test:
  steps:
    - Start PostgreSQL service (Docker)
    - Install dependencies
    - Run migrations
    - Run unit tests: pytest tests/unit -v
    - Run integration tests: pytest tests/integration -v
    - Run coverage: pytest --cov=src/paygateway --cov-report=xml
    - Upload coverage report
```

E2E tests run on a separate schedule (nightly or on release branches) since they require Stripe test API calls.
