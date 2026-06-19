# Payment Gateway Core Service — Implementation Plan

## Overview

This plan defines the phased implementation approach for the Payment Gateway Core Service. Each phase builds on the previous one. The implementation run should follow this order strictly.

## Phase 1: Project Scaffolding

**Goal:** Set up the project structure, dependencies, configuration, and database foundation.

### Tasks
1. Create project directory structure matching `system-vision.md` section 18.
2. Create `pyproject.toml` with all dependencies.
3. Create `requirements.txt` and `requirements-dev.txt`.
4. Create `.gitignore` (Python, IDE, .env, __pycache__, etc.).
5. Create `.env.example` with all required environment variables.
6. Create `src/paygateway/__init__.py` and `src/paygateway/config.py` (Pydantic Settings class).
7. Create `src/paygateway/main.py` (FastAPI app with CORS, versioned router, lifespan).
8. Create database session management (`src/paygateway/db/`).
9. Set up Alembic configuration (`alembic.ini`, `migrations/env.py`).
10. Create `Dockerfile` and `docker-compose.yml` (app + PostgreSQL + Redis).
11. Create initial pytest configuration (`tests/conftest.py`, `pyproject.toml` pytest section).

**Exit criteria:** `uvicorn src.paygateway.main:app` starts, `/health` returns 200, database connects, Alembic runs.

## Phase 2: Data Models and Migrations

**Goal:** Define all SQLAlchemy models and create the initial database migration.

### Tasks
1. Create SQLAlchemy base model with common fields (`src/paygateway/db/base.py`).
2. Create `models/payment.py` — Payment model.
3. Create `models/refund.py` — Refund model.
4. Create `models/webhook_event.py` — WebhookEvent model.
5. Create `models/idempotency.py` — IdempotencyRecord model.
6. Create `models/audit_log.py` — AuditLog model.
7. Create `models/api_key.py` — ApiKey model.
8. Create `models/reconciliation_report.py` — ReconciliationReport model.
9. Create `models/__init__.py` exporting all models.
10. Generate initial Alembic migration.
11. Test migration up and down.

**Exit criteria:** All tables created in database. Migration reversible. Models importable.

## Phase 3: Pydantic Schemas

**Goal:** Define all request/response schemas for API validation.

### Tasks
1. Create `schemas/common.py` — shared types (ErrorResponse, PaginationParams, PaginatedResponse).
2. Create `schemas/payment.py` — CreatePaymentRequest, PaymentResponse, PaymentListResponse, PaymentFilters.
3. Create `schemas/refund.py` — CreateRefundRequest, RefundResponse, RefundListResponse.
4. Create `schemas/webhook.py` — (internal schemas, webhook doesn't have a request schema per se).
5. Create `schemas/reconciliation.py` — ReconciliationRunRequest, ReportResponse.
6. Create `schemas/health.py` — HealthResponse, InfoResponse.
7. Create `schemas/__init__.py`.

**Exit criteria:** All schemas importable. Validation rules enforce constraints from spec.

## Phase 4: Provider Abstraction and Stripe Adapter

**Goal:** Implement the provider interface and Stripe adapter.

### Tasks
1. Create `providers/base.py` — abstract `PaymentProvider` class with methods: `create_payment_intent`, `confirm_payment_intent`, `cancel_payment_intent`, `create_refund`, `get_payment_intent`, `get_refund`, `verify_webhook_signature`, `list_payment_intents` (for reconciliation).
2. Create `providers/stripe_provider.py` — Stripe implementation using `stripe` Python SDK.
3. Create `providers/__init__.py` — provider factory function.
4. Write unit tests for Stripe provider (mocked Stripe SDK calls).

**Exit criteria:** Provider interface defined. Stripe adapter implements all methods. Unit tests pass.

## Phase 5: Core Services

**Goal:** Implement business logic services.

### Tasks
1. Create `services/idempotency_service.py` — check/store/retrieve idempotent responses.
2. Create `services/audit_service.py` — append audit log entries.
3. Create `services/payment_service.py` — create, confirm, cancel, get, list payments.
4. Create `services/refund_service.py` — create, get, list refunds.
5. Create `services/webhook_service.py` — verify, deduplicate, process events, dispatch to handlers.
6. Create `services/reconciliation_service.py` — run reconciliation, generate reports.
7. Create `services/__init__.py`.
8. Write unit tests for all services (mocked provider and repository).

**Exit criteria:** All service methods implemented. Business rules enforced. Unit tests pass.

## Phase 6: Middleware

**Goal:** Implement cross-cutting concerns as middleware.

### Tasks
1. Create `middleware/authentication.py` — API key and JWT validation.
2. Create `middleware/rate_limiting.py` — rate limiting per API key.
3. Create `middleware/idempotency.py` — idempotency key extraction and enforcement.
4. Create `middleware/correlation.py` — request correlation ID generation/propagation.
5. Create `middleware/__init__.py`.
6. Write unit tests for middleware.

**Exit criteria:** Middleware intercepts requests correctly. Auth rejects unauthorized. Rate limiter throttles excess.

## Phase 7: API Routes

**Goal:** Wire services to HTTP endpoints.

### Tasks
1. Create `dependencies.py` — FastAPI dependency injection (get_db, get_provider, get_current_user).
2. Create `routes/health.py` — `GET /health`, `GET /info`.
3. Create `routes/payments.py` — CRUD endpoints for payments.
4. Create `routes/refunds.py` — refund endpoints.
5. Create `routes/webhooks.py` — webhook ingestion endpoint.
6. Create `routes/reconciliation.py` — admin reconciliation endpoints.
7. Create `routes/__init__.py` — aggregate router.
8. Register all routes in `main.py`.
9. Write integration tests for all endpoints.

**Exit criteria:** All endpoints respond correctly. OpenAPI docs generated. Integration tests pass.

## Phase 8: Background Jobs

**Goal:** Implement scheduled/background tasks.

### Tasks
1. Set up background task infrastructure (ARQ with Redis, or FastAPI BackgroundTasks for simple cases).
2. Implement idempotency record cleanup job (delete expired records).
3. Implement webhook event cleanup job (archive old events).
4. Implement scheduled reconciliation job.
5. Write tests for background jobs.

**Exit criteria:** Jobs run on schedule. Cleanup works. Reconciliation runs periodically.

## Phase 9: Integration and E2E Testing

**Goal:** Full-flow testing with Stripe test mode.

### Tasks
1. Create integration test fixtures (test database, test Stripe keys).
2. Write integration tests: full payment flow (create → confirm → webhook → status).
3. Write integration tests: refund flow (create → refund → webhook → status).
4. Write integration tests: idempotency (duplicate requests return same response).
5. Write integration tests: webhook signature verification (valid and invalid).
6. Write integration tests: rate limiting behavior.
7. Write integration tests: reconciliation flow.
8. Write E2E test for complete payment lifecycle.

**Exit criteria:** All integration and E2E tests pass with Stripe test mode. No security test failures.

## Phase 10: Documentation and Finalization

**Goal:** Ensure the project is production-ready and well-documented.

### Tasks
1. Update `README.md` with setup instructions, API overview, environment variables.
2. Verify OpenAPI/Swagger docs are complete and accurate.
3. Create `CONTRIBUTING.md` with development workflow.
4. Review and update `.env.example`.
5. Verify Docker setup works end-to-end.
6. Run full test suite.
7. Security review pass.

**Exit criteria:** Project runs from clean clone. All tests pass. Documentation complete.

## Implementation Order Summary

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10
```

Each phase depends on the previous. Do not skip phases. If a phase is partially complete from a prior session, continue from where it left off.
