# Payment Gateway Core Service — Implementation Tasks

## Overview

These are the detailed implementation tasks for the Payment Gateway Core Service, organized by phase from `plan.md`. Each task includes the file(s) to create/modify, acceptance criteria, and dependencies.

The implementation session should execute these tasks sequentially within each phase.

---

## Phase 1: Project Scaffolding

### T1.1: Create project directory structure

**Files:** All directories under `src/paygateway/` and `tests/`
**Action:** Create the full directory tree with `__init__.py` files.
**Acceptance:** All directories exist. All `__init__.py` files present.

### T1.2: Create pyproject.toml

**File:** `pyproject.toml`
**Action:** Define project metadata, dependencies, dev dependencies, and tool configuration.
**Dependencies:**
- Runtime: `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `sqlalchemy[asyncio]>=2.0.36`, `asyncpg>=0.30.0`, `alembic>=1.14.0`, `pydantic>=2.10.0`, `pydantic-settings>=2.6.0`, `stripe>=8.0.0`, `httpx>=0.27.0`, `python-jose[cryptography]>=3.3.0`, `passlib[bcrypt]>=1.7.4`, `redis>=5.2.0`, `structlog>=24.4.0`
- Dev: `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=6.0.0`, `httpx>=0.27.0`, `factory-boy>=3.3.0`, `ruff>=0.8.0`, `mypy>=1.13.0`, `aiosqlite>=0.20.0`
**Acceptance:** `pip install -e .` succeeds. `pip install -e ".[dev]"` installs dev deps.

### T1.3: Create requirements files

**Files:** `requirements.txt`, `requirements-dev.txt`
**Action:** Pin all dependencies with specific versions.
**Acceptance:** `pip install -r requirements.txt` succeeds.

### T1.4: Create .gitignore

**File:** `.gitignore`
**Action:** Add patterns for Python, IDE, .env, __pycache__, .pytest_cache, dist, build, *.egg-info, .mypy_cache, .ruff_cache.
**Acceptance:** `git status` does not show unwanted files.

### T1.5: Create .env.example

**File:** `.env.example`
**Action:** List all environment variables with placeholder values and comments.
**Variables:** DATABASE_URL, REDIS_URL, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_API_VERSION, JWT_SECRET_KEY, JWT_ALGORITHM, ALLOWED_ORIGINS, API_KEY_SALT, LOG_LEVEL, ENVIRONMENT.
**Acceptance:** File documents all required configuration.

### T1.6: Create config module

**File:** `src/paygateway/config.py`
**Action:** Create Pydantic Settings class loading from environment variables. Include all settings from .env.example. Add validation (e.g., STRIPE_API_VERSION format, ENVIRONMENT in [development, staging, production]).
**Acceptance:** `Settings()` loads from .env. Missing required vars raise validation error.

### T1.7: Create FastAPI application

**File:** `src/paygateway/main.py`
**Action:** Create FastAPI app with lifespan handler, CORS middleware, versioned router mount at `/api/v1`, health/info endpoints directly on root.
**Acceptance:** `uvicorn src.paygateway.main:app --reload` starts. `GET /health` returns 200.

### T1.8: Create database session management

**Files:** `src/paygateway/db/__init__.py`, `src/paygateway/db/session.py`, `src/paygateway/db/base.py`
**Action:** Create async SQLAlchemy engine and session factory. Create `get_db` async generator for FastAPI dependency injection. Create declarative base class.
**Acceptance:** Database session can be obtained via dependency injection.

### T1.9: Set up Alembic

**Files:** `alembic.ini`, `src/paygateway/migrations/env.py`, `src/paygateway/migrations/versions/` (empty)
**Action:** Configure Alembic for async SQLAlchemy. Point at DATABASE_URL from settings. Import all models in env.py for autogenerate.
**Acceptance:** `alembic revision --autogenerate -m "initial"` creates a migration.

### T1.10: Create Docker setup

**Files:** `Dockerfile`, `docker-compose.yml`
**Action:** Multi-stage Dockerfile (build + runtime). docker-compose with services: app, postgres, redis.
**Acceptance:** `docker-compose up` starts all services. App connects to database.

### T1.11: Create test configuration

**Files:** `tests/__init__.py`, `tests/conftest.py`
**Action:** Create shared fixtures: test database session (SQLite async for unit tests), test FastAPI client, test API keys, mock provider.
**Acceptance:** `pytest` runs with no errors (even with no tests yet).

---

## Phase 2: Data Models and Migrations

### T2.1: Create base model

**File:** `src/paygateway/db/base.py`
**Action:** Create SQLAlchemy declarative base with common mixin (id UUID, created_at, updated_at).
**Acceptance:** Base class importable. Common fields work on subclasses.

### T2.2: Create Payment model

**File:** `src/paygateway/models/payment.py`
**Action:** Implement Payment model per data-model.md section 3.1.
**Acceptance:** Model has all columns, indexes, and constraints.

### T2.3: Create Refund model

**File:** `src/paygateway/models/refund.py`
**Action:** Implement Refund model per data-model.md section 3.2. FK to Payment.
**Acceptance:** Model has all columns. FK enforced.

### T2.4: Create WebhookEvent model

**File:** `src/paygateway/models/webhook_event.py`
**Action:** Implement per data-model.md section 3.3.
**Acceptance:** Unique constraint on event_id.

### T2.5: Create IdempotencyRecord model

**File:** `src/paygateway/models/idempotency.py`
**Action:** Implement per data-model.md section 3.4.
**Acceptance:** Unique constraint on key. expires_at indexed.

### T2.6: Create AuditLog model

**File:** `src/paygateway/models/audit_log.py`
**Action:** Implement per data-model.md section 3.5. Append-only (no update/delete methods).
**Acceptance:** All fields present. Indexes on timestamp, action, resource.

### T2.7: Create ApiKey model

**File:** `src/paygateway/models/api_key.py`
**Action:** Implement per data-model.md section 3.6.
**Acceptance:** key_hash unique. role field present.

### T2.8: Create ReconciliationReport model

**File:** `src/paygateway/models/reconciliation_report.py`
**Action:** Implement per data-model.md section 3.7.
**Acceptance:** All fields present.

### T2.9: Create models __init__.py

**File:** `src/paygateway/models/__init__.py`
**Action:** Import and export all models.
**Acceptance:** `from paygateway.models import Payment, Refund, ...` works.

### T2.10: Generate initial migration

**Action:** Run `alembic revision --autogenerate -m "create_initial_tables"`.
**Acceptance:** Migration creates all 7 tables. Downgrade drops all tables.

### T2.11: Test migration

**Action:** Run `alembic upgrade head` then `alembic downgrade base` then `alembic upgrade head`.
**Acceptance:** No errors. All tables created.

---

## Phase 3: Pydantic Schemas

### T3.1: Common schemas

**File:** `src/paygateway/schemas/common.py`
**Action:** Create ErrorResponse, ErrorDetail, PaginationParams, PaginatedResponse[T] (generic).
**Acceptance:** Schemas validate correctly. Generic pagination works with any data type.

### T3.2: Payment schemas

**File:** `src/paygateway/schemas/payment.py`
**Action:** Create CreatePaymentRequest (with amount, currency, customer_id, description, metadata validations), PaymentResponse, PaymentListFilters.
**Acceptance:** Invalid amounts rejected. Invalid currencies rejected. Metadata size limits enforced.

### T3.3: Refund schemas

**File:** `src/paygateway/schemas/refund.py`
**Action:** Create CreateRefundRequest (optional amount, reason), RefundResponse.
**Acceptance:** Negative amount rejected. Reason length limited.

### T3.4: Webhook schemas

**File:** `src/paygateway/schemas/webhook.py`
**Action:** Create WebhookResponse (simple {received: true}).
**Acceptance:** Schema importable.

### T3.5: Reconciliation schemas

**File:** `src/paygateway/schemas/reconciliation.py`
**Action:** Create ReconciliationRunRequest (date_range_start, date_range_end), ReconciliationReportResponse.
**Acceptance:** Date validation works. Response includes discrepancy details.

### T3.6: Health schemas

**File:** `src/paygateway/schemas/health.py`
**Action:** Create HealthResponse, InfoResponse.
**Acceptance:** Schemas match API contract.

---

## Phase 4: Provider Abstraction and Stripe Adapter

### T4.1: Abstract provider interface

**File:** `src/paygateway/providers/base.py`
**Action:** Implement abstract PaymentProvider class, data classes (ProviderPaymentIntent, ProviderRefund, ProviderWebhookEvent), and error hierarchy per provider-interface.md.
**Acceptance:** Abstract methods defined. Cannot instantiate directly. Error classes have correct hierarchy.

### T4.2: Stripe provider adapter

**File:** `src/paygateway/providers/stripe_provider.py`
**Action:** Implement StripeProvider per stripe-provider.md. All 8 abstract methods implemented. Status mapping. Error mapping. Async via asyncio.to_thread.
**Acceptance:** All methods implemented. Status mapping covers all Stripe statuses. Error mapping covers all Stripe exceptions.

### T4.3: Provider factory

**File:** `src/paygateway/providers/__init__.py`
**Action:** Implement get_payment_provider factory function.
**Acceptance:** `get_payment_provider("stripe", config)` returns StripeProvider. Unknown provider raises ValueError.

### T4.4: Provider unit tests

**File:** `tests/unit/test_stripe_provider.py`
**Action:** Test all Stripe provider methods with mocked stripe SDK. Test status mapping. Test error mapping. Test webhook verification.
**Acceptance:** All tests pass. Full coverage of status and error mapping.

---

## Phase 5: Core Services

### T5.1: Idempotency service

**File:** `src/paygateway/services/idempotency_service.py`
**Action:** Implement check_and_store (returns cached response or None), store_response, cleanup_expired.
**Acceptance:** Duplicate key + same body returns cached. Duplicate key + different body raises error. Expired keys cleaned up.

### T5.2: Audit service

**File:** `src/paygateway/services/audit_service.py`
**Action:** Implement log_action (creates AuditLog entry). Accept all fields from data model.
**Acceptance:** Audit entries created. No update/delete exposed.

### T5.3: Payment service

**File:** `src/paygateway/services/payment_service.py`
**Action:** Implement create_payment, confirm_payment, cancel_payment, get_payment, list_payments. Uses provider interface. Creates audit entries. Validates state transitions.
**Acceptance:** Payments created via provider. State transitions enforced. Audit logged.

### T5.4: Refund service

**File:** `src/paygateway/services/refund_service.py`
**Action:** Implement create_refund, get_refund, list_refunds_for_payment. Validates refundable state. Validates amount <= remaining. Uses provider. Creates audit entries.
**Acceptance:** Refunds created. Over-refund rejected. Non-refundable status rejected.

### T5.5: Webhook service

**File:** `src/paygateway/services/webhook_service.py`
**Action:** Implement process_webhook_event. Verify via provider. Deduplicate by event_id. Dispatch to handler by event_type. Update payment/refund status. Create audit entries. Handle state machine rules.
**Acceptance:** Events processed idempotently. Status updated correctly. Invalid transitions rejected.

### T5.6: Reconciliation service

**File:** `src/paygateway/services/reconciliation_service.py`
**Action:** Implement run_reconciliation per reconciliation.md. Fetch internal records. Fetch provider records (paginated). Compare. Generate report. Store report.
**Acceptance:** Discrepancies detected. Report generated and stored.

### T5.7: Service unit tests

**Files:** `tests/unit/test_payment_service.py`, `tests/unit/test_refund_service.py`, `tests/unit/test_webhook_service.py`, `tests/unit/test_idempotency_service.py`, `tests/unit/test_reconciliation_service.py`
**Action:** Write unit tests per testing-strategy.md section 5.
**Acceptance:** All test cases pass. Services tested with mocked dependencies.

---

## Phase 6: Middleware

### T6.1: Authentication middleware

**File:** `src/paygateway/middleware/authentication.py`
**Action:** Implement API key lookup (by prefix, verify hash) and JWT validation. Extract role. Attach current user/key info to request state.
**Acceptance:** Valid key accepted. Invalid key rejected (401). Role extracted.

### T6.2: Rate limiting middleware

**File:** `src/paygateway/middleware/rate_limiting.py`
**Action:** Implement sliding window rate limiter using Redis (with in-memory fallback). Configurable limits per endpoint category. Return 429 with Retry-After header.
**Acceptance:** Requests within limit pass. Excess requests get 429. Headers present.

### T6.3: Idempotency middleware

**File:** `src/paygateway/middleware/idempotency.py`
**Action:** Extract Idempotency-Key from header on POST requests. Return 422 if missing. Check idempotency service for cached response. If cached, return it. Otherwise proceed and cache response.
**Acceptance:** Missing key rejected. Cached response returned for duplicate. New request processed.

### T6.4: Correlation ID middleware

**File:** `src/paygateway/middleware/correlation.py`
**Action:** Extract X-Request-ID from request or generate UUID. Attach to request state and response header. Include in structured logs.
**Acceptance:** Response includes X-Request-ID. Logs include correlation ID.

### T6.5: Middleware unit tests

**Files:** `tests/unit/test_authentication.py`, `tests/unit/test_rate_limiting.py`
**Action:** Test auth with valid/invalid keys. Test rate limiting thresholds.
**Acceptance:** All tests pass.

---

## Phase 7: API Routes

### T7.1: FastAPI dependencies

**File:** `src/paygateway/dependencies.py`
**Action:** Create dependency functions: get_db, get_provider, get_current_user (from auth middleware), require_role(roles) dependency factory.
**Acceptance:** Dependencies injectable into route functions.

### T7.2: Health routes

**File:** `src/paygateway/routes/health.py`
**Action:** Implement `GET /health` (check db + Stripe connectivity) and `GET /info` (return version, environment).
**Acceptance:** Health returns status of each check. Info returns version.

### T7.3: Payment routes

**File:** `src/paygateway/routes/payments.py`
**Action:** Implement all payment endpoints per api-contract.md section 5.2. Wire to payment service. Apply auth and idempotency dependencies.
**Acceptance:** All endpoints respond per contract. Auth enforced. Idempotency enforced.

### T7.4: Refund routes

**File:** `src/paygateway/routes/refunds.py`
**Action:** Implement refund endpoints per api-contract.md section 5.3.
**Acceptance:** All endpoints respond per contract.

### T7.5: Webhook routes

**File:** `src/paygateway/routes/webhooks.py`
**Action:** Implement Stripe webhook endpoint per api-contract.md section 5.4. Read raw body. Pass to webhook service.
**Acceptance:** Valid webhooks processed. Invalid signatures rejected.

### T7.6: Reconciliation routes

**File:** `src/paygateway/routes/reconciliation.py`
**Action:** Implement reconciliation endpoints per api-contract.md section 5.5. Admin role required.
**Acceptance:** Reconciliation triggered. Reports retrievable.

### T7.7: Router aggregation

**Files:** `src/paygateway/routes/__init__.py`, update `src/paygateway/main.py`
**Action:** Create aggregate v1 router. Include all sub-routers. Register in main app.
**Acceptance:** All endpoints accessible under /api/v1/. OpenAPI docs show all endpoints.

### T7.8: Integration tests

**Files:** `tests/integration/test_payment_api.py`, `tests/integration/test_refund_api.py`, `tests/integration/test_webhook_api.py`, `tests/integration/test_reconciliation_api.py`, `tests/integration/test_health_api.py`, `tests/integration/test_idempotency_api.py`
**Action:** Write integration tests per testing-strategy.md section 6.
**Acceptance:** All tests pass against test database.

---

## Phase 8: Background Jobs

### T8.1: Job infrastructure

**File:** `src/paygateway/jobs/__init__.py`, `src/paygateway/jobs/scheduler.py`
**Action:** Set up simple background task scheduler (APScheduler or FastAPI lifespan-based). Configure job schedule.
**Acceptance:** Jobs can be registered and run on schedule.

### T8.2: Idempotency cleanup job

**File:** `src/paygateway/jobs/cleanup.py`
**Action:** Delete expired idempotency records. Run daily.
**Acceptance:** Expired records removed. Active records untouched.

### T8.3: Webhook cleanup job

**File:** `src/paygateway/jobs/cleanup.py` (add to same file)
**Action:** Archive/delete processed webhook events older than 90 days.
**Acceptance:** Old events cleaned up. Recent events untouched.

### T8.4: Scheduled reconciliation

**File:** `src/paygateway/jobs/reconciliation.py`
**Action:** Trigger reconciliation for previous day. Run daily at configurable time.
**Acceptance:** Reconciliation runs automatically. Report stored.

---

## Phase 9: Integration and E2E Testing

### T9.1: Test fixtures for Stripe

**File:** `tests/conftest.py` (update)
**Action:** Add fixtures for Stripe test mode. Create helper to generate test webhook events with valid signatures.
**Acceptance:** Fixtures usable in e2e tests.

### T9.2: Payment lifecycle E2E test

**File:** `tests/e2e/test_payment_flow.py`
**Action:** Test: create payment → confirm via Stripe test API → simulate webhook → verify status.
**Acceptance:** Full flow passes.

### T9.3: Refund lifecycle E2E test

**File:** `tests/e2e/test_refund_flow.py`
**Action:** Test: create + confirm payment → refund → simulate webhook → verify statuses.
**Acceptance:** Full flow passes.

### T9.4: Error scenario tests

**File:** `tests/e2e/test_error_scenarios.py`
**Action:** Test declined cards, invalid webhooks, over-refunds, duplicate keys.
**Acceptance:** All error scenarios handled correctly.

---

## Phase 10: Documentation and Finalization

### T10.1: Update README.md

**File:** `README.md`
**Action:** Add project description, setup instructions, environment variables, API overview, development workflow, testing instructions.
**Acceptance:** New developer can set up and run the project from README alone.

### T10.2: Verify OpenAPI docs

**Action:** Start the server. Check `/docs` (Swagger UI) and `/redoc`. Verify all endpoints documented with correct schemas.
**Acceptance:** All endpoints visible. Schemas accurate.

### T10.3: Create .env.example review

**File:** `.env.example`
**Action:** Ensure all variables are listed with descriptions and safe placeholder values.
**Acceptance:** Copy `.env.example` to `.env`, fill in Stripe test keys, service starts.

### T10.4: Docker end-to-end verification

**Action:** `docker-compose up --build`. Verify app starts, connects to database, runs migrations, health check passes.
**Acceptance:** Clean `docker-compose up` works.

### T10.5: Full test suite run

**Action:** Run `pytest tests/ -v --cov=src/paygateway`.
**Acceptance:** All tests pass. Coverage meets targets (>= 85% overall).

### T10.6: Security review

**Action:** Review: no secrets in code, no raw SQL, auth on all protected endpoints, rate limiting active, webhook signatures verified, input validation complete, CORS configured.
**Acceptance:** No security issues found.

---

## Implementation Instructions for the Execution Session

1. Read `system-vision.md` first.
2. Read all files in `specs/payment-gateway-core/`.
3. Execute tasks in order: T1.1 → T1.2 → ... → T10.6.
4. Skip tasks that are already complete from a prior session.
5. Run tests after each phase.
6. If context limits are reached, write a continuation note per `system-vision.md` section 4.
