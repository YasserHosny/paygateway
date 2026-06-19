# System Vision: Payment Gateway Core Service

## 1. Role and Responsibility

Claude Code should act as:

- Senior software architect
- Principal backend engineer
- Security engineer
- Stripe payment integration expert
- SpecKit / Specification-Driven Development (SDD) practitioner

The goal is to design and later implement a production-grade, reusable Payment Gateway Core Service that can be consumed by multiple platforms.

The service should support:

- Multiple web applications
- Mobile applications
- Desktop applications
- Future third-party integrations
- Internal admin/back-office systems
- Other backend services

Expected technology ecosystem:

- Python backend/core service
- Angular web applications
- Flutter mobile applications
- Future desktop or API-based clients

The Payment Gateway Core Service must be designed so that Angular, Flutter, desktop apps, and other platforms consume it through clean APIs.

The core payment logic must not be coupled to Angular, Flutter, desktop, or any UI framework.

---

## 2. Working Rules

Claude Code must not stop to ask clarification questions.

If any requirement is missing, ambiguous, or has multiple valid options:

- Make the best professional recommendation.
- Document the assumption inside this file or in `/specs/payment-gateway-core/assumptions.md`.
- Continue the work.

Prefer decisions that are:

- Secure
- Scalable
- Maintainable
- Extensible
- Production-minded
- Testable
- Provider-agnostic at the core level
- Stripe-ready for the first real implementation

Claude Code should act as if it is responsible for delivering the first production-ready version.

---

## 3. SpecKit / SDD Rule

Use a SpecKit / Specification-Driven Development approach.

Claude Code should apply the appropriate SpecKit workflow and commands for:

- Specification creation
- Planning
- Clarification or assumption documentation
- Technical design
- Task breakdown

### Critical Rule: Do Not Implement

Claude Code **must not** run or apply:

```
speckit.implement
```

The implementation phase will be executed later using a cheaper mode/model.

In the current phase, Claude Code is responsible for preparing everything before implementation:

- Analyze the repository.
- Create or update the specification.
- Create the implementation plan.
- Create the technical design.
- Create the data model.
- Create API contracts.
- Create security design.
- Create Stripe provider integration design.
- Create webhook flow.
- Create reconciliation design.
- Create testing strategy.
- Create detailed implementation tasks.
- Prepare the project so another Claude Code run can execute `speckit.implement` later.

**Do not implement code in this phase.**

**Do not run `speckit.implement` in this phase.**

---

## 4. Credit, Context, and Session Limit Behavior

If execution credits, context limits, or session limits are reached, Claude Code must not abandon the task.

Before stopping, Claude Code must write a detailed continuation note including:

1. What has been completed.
2. What files were created or modified.
3. What remains.
4. Exact next steps.
5. The exact SpecKit command that should be run next.
6. Any commands/tests that should be run next.
7. Any important assumptions already made.
8. Any risks or open items that the next run should know.

After that, Claude Code should pause so the user can resume after the 5-hour limit reset by pasting the continuation note back into Claude Code.

Claude Code must not restart from scratch after resume. It should continue from the existing files and notes.

---

## 5. Project Goal

Create a reusable Payment Gateway Core Service.

The service should act as the central payment orchestration layer between client applications and Stripe.

The core service must support:

- Payment initiation
- Payment confirmation
- Payment status tracking
- Refunds (full and partial)
- Webhook handling
- Payment reconciliation support
- Idempotency (all mutating endpoints must accept and enforce idempotency keys)
- Audit logging (every payment-related action must be logged with actor, timestamp, action, and outcome)
- Provider abstraction (core logic decoupled from Stripe specifics)
- Stripe integration (first and default provider)
- Secure API access (authentication, authorization, rate limiting, input validation)
- Multi-platform client usage
- Future extensibility for additional payment providers (e.g., PayPal, Adyen, Square)

The system must not be tightly coupled to:

- One frontend
- One mobile app
- One desktop app
- One provider implementation

Stripe is the selected gateway provider for the first production-ready implementation.

---

## 6. Payment Provider Decision

Stripe is the selected payment gateway provider for the first production-ready implementation.

The system should still be designed with provider abstraction, but Stripe should be treated as the primary/default provider.

### Important Rules

- Implement Stripe as the real provider adapter in the implementation plan.
- Keep the provider abstraction clean so another provider (e.g., PayPal, Adyen) can be added later.
- Do not hardcode Stripe credentials.
- Use environment variables for Stripe configuration:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PUBLISHABLE_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_API_VERSION` (pin to a specific version, e.g., `2024-12-18`)
- Use Stripe test mode for local development and testing.
- Design the service so Angular, Flutter, desktop apps, and other clients never call Stripe directly for sensitive backend operations.
- All payment creation, confirmation, refunds, webhook processing, and reconciliation should go through the Payment Gateway Core Service.
- Angular and Flutter may use Stripe client SDKs only where appropriate for safe client-side confirmation flows (e.g., `stripe.confirmPayment` using the client secret returned by the backend), but never with secret keys.

### Stripe Integration Patterns

- Use Stripe PaymentIntents as the primary payment flow.
- Support Stripe SetupIntents for saving payment methods without immediate charge.
- Use Stripe Webhooks for asynchronous event handling (payment success, failure, disputes, refunds).
- Use Stripe idempotency keys for all mutating API calls to Stripe.
- Store Stripe customer IDs and map them to internal user/account identifiers.
- Never store raw card numbers, CVVs, or sensitive cardholder data. Rely on Stripe tokenization.

---

## 7. Expected Stack Context

### Assumption

The repository is currently empty (initial commit with README only). Since no backend framework exists, this project will use **Python + FastAPI** as the recommended backend implementation direction.

If a future run discovers the repository has adopted another valid stack, adapt professionally to the existing stack instead of forcing Python/FastAPI.

### Backend / Core Service

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **API Style:** REST (OpenAPI/Swagger auto-generated)
- **Database:** Supabase (managed PostgreSQL) for both local development and production
- **ORM:** SQLAlchemy 2.x (async support)
- **Migrations:** Alembic
- **Validation/Modeling:** Pydantic v2
- **Async:** Async-friendly design using `asyncio`, `httpx` for outbound HTTP
- **Testing:** pytest, pytest-asyncio, factory_boy for fixtures
- **Linting/Formatting:** ruff, black, mypy
- **Dependency Management:** pip + requirements files or Poetry
- **Containerization:** Docker + docker-compose for local dev

### Web Application (Angular)

- Angular should consume the Payment Gateway Core Service through REST APIs only.
- Do not place payment business rules in Angular.
- Angular should only handle:
  - UI rendering and UX
  - Client-side form validation
  - Safe Stripe.js / `@stripe/stripe-js` usage for collecting payment details and confirming payments using client secrets
  - User interaction and navigation
- Angular receives a `client_secret` from the backend and uses it with Stripe.js to complete the payment flow on the client side.
- Angular must never have access to `STRIPE_SECRET_KEY`.

### Mobile Application (Flutter)

- Flutter should consume the same Payment Gateway Core Service APIs.
- Do not duplicate payment business rules in Flutter.
- Flutter should only handle:
  - UI rendering and UX
  - Client-side form validation
  - Safe `flutter_stripe` SDK usage for collecting payment details and confirming payments
  - User interaction and navigation
- Flutter receives a `client_secret` from the backend and uses it with the Stripe mobile SDK to complete the payment flow.
- Flutter must never have access to `STRIPE_SECRET_KEY`.

### Future Clients

- Desktop applications (Electron, native, etc.)
- Third-party integrations via API keys / OAuth
- Internal admin systems
- Other backend services (service-to-service calls)

Design APIs and contracts so all clients can integrate consistently using the same REST endpoints.

---

## 8. SpecKit / Specification-Driven Development Flow

Claude Code should follow this workflow:

1. Inspect the current repository.
2. Identify existing stack, conventions, package manager, architecture, and test framework.
3. Apply the relevant SpecKit workflow for:
   - Specification creation
   - Planning
   - Clarification or assumption documentation
   - Technical design
   - Task breakdown
4. **Do not execute `speckit.implement`.**
5. Stop after implementation tasks are fully prepared.
6. Provide clear instructions for the later implementation run.

### Target Specification Structure

```
/specs
  /payment-gateway-core
    spec.md                  # Full specification
    plan.md                  # Implementation plan with phases
    tasks.md                 # Detailed implementation tasks
    data-model.md            # Database schema and entity design
    api-contract.md          # REST API endpoints, request/response schemas
    security.md              # Authentication, authorization, encryption, secrets management
    provider-interface.md    # Abstract provider interface definition
    stripe-provider.md       # Stripe-specific adapter design
    webhook-flow.md          # Webhook ingestion, verification, processing, retry
    reconciliation.md        # Payment reconciliation design
    testing-strategy.md      # Unit, integration, e2e test strategy
    client-integration.md    # Angular, Flutter, and generic client integration guide
    assumptions.md           # Documented assumptions and recommendations
    risks.md                 # Risks and mitigations
```

---

## 9. Architecture Overview

### High-Level Architecture

```
Clients (Angular, Flutter, Desktop, API consumers)
    |
    | REST API (HTTPS)
    |
[API Gateway / Load Balancer] (optional, future)
    |
[Payment Gateway Core Service - FastAPI]
    |
    +-- Authentication & Authorization Layer
    +-- Rate Limiting & Throttling
    +-- Request Validation (Pydantic)
    +-- Idempotency Layer
    +-- Payment Orchestration Engine
    |       |
    |       +-- Provider Abstraction Layer
    |       |       |
    |       |       +-- Stripe Provider Adapter
    |       |       +-- [Future: PayPal Adapter]
    |       |       +-- [Future: Adyen Adapter]
    |       |
    |       +-- Refund Engine
    |       +-- Reconciliation Engine
    |
    +-- Webhook Ingestion Endpoint
    |       |
    |       +-- Signature Verification
    |       +-- Event Processing Pipeline
    |       +-- Idempotent Event Handling
    |
    +-- Audit Logging Service
    +-- Database (Supabase / PostgreSQL)
    +-- Background Task Queue (optional: Celery/ARQ for retries, reconciliation jobs)
```

### Key Design Principles

1. **Provider Abstraction:** All payment operations go through a `PaymentProvider` interface. Stripe is the first concrete implementation.
2. **Idempotency:** Every mutating API endpoint accepts an `Idempotency-Key` header. The service deduplicates requests within a configurable TTL (default: 24 hours).
3. **Webhook Safety:** Webhooks are verified using provider-specific signature verification. Events are processed idempotently (duplicate event IDs are ignored).
4. **Audit Trail:** Every payment action (create, confirm, refund, status change) is logged to an append-only audit log table.
5. **Security First:** No raw card data. API authentication required. Rate limiting on sensitive endpoints. Input validation on all endpoints.
6. **Separation of Concerns:** Business logic in service layer, HTTP handling in route layer, data access in repository layer.

---

## 10. Core Functional Requirements

### 10.1 Payment Initiation

- Client sends payment request (amount, currency, metadata, idempotency key).
- Backend creates a PaymentIntent via Stripe.
- Backend returns `client_secret` and internal payment ID to client.
- Client uses `client_secret` with Stripe.js/Flutter Stripe SDK to collect card details and confirm payment.

### 10.2 Payment Confirmation

- Client-side confirmation happens via Stripe SDK (Stripe.js or flutter_stripe).
- Backend is notified of the result via Stripe webhooks.
- Backend updates internal payment status based on webhook events.
- Clients can also poll a status endpoint to check payment state.

### 10.3 Payment Status Tracking

- `GET /payments/{payment_id}` returns current payment status, amount, provider reference, timestamps.
- Supports filtering/listing payments by status, date range, customer.

### 10.4 Refunds

- `POST /payments/{payment_id}/refund` initiates a full or partial refund.
- Accepts amount (for partial refund), reason, and idempotency key.
- Backend calls Stripe Refunds API.
- Refund status tracked via webhooks.
- Audit log entry created for every refund action.

### 10.5 Webhook Handling

- `POST /webhooks/stripe` receives Stripe webhook events.
- Verifies signature using `STRIPE_WEBHOOK_SECRET`.
- Processes events idempotently (stores processed event IDs).
- Handles key events:
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
  - `charge.refunded`
  - `charge.dispute.created`
  - `charge.dispute.closed`
- Updates internal payment records accordingly.

### 10.6 Reconciliation

- Periodic reconciliation job compares internal payment records against Stripe records.
- Flags discrepancies (missing payments, amount mismatches, status mismatches).
- Generates reconciliation reports.
- Can be triggered manually via admin endpoint or run on a schedule.

### 10.7 Idempotency

- All mutating endpoints accept `Idempotency-Key` header.
- If the same key is sent again within TTL, return the cached response without re-executing the operation.
- Idempotency records stored in database with key, request hash, response, expiry.
- Stripe API calls also use idempotency keys (forwarded or derived from the client key).

### 10.8 Audit Logging

- Append-only `audit_log` table.
- Fields: `id`, `timestamp`, `actor_id`, `actor_type` (user, system, webhook), `action`, `resource_type`, `resource_id`, `details` (JSON), `ip_address`, `outcome` (success/failure).
- Every payment-related mutation is logged.
- Audit logs are never deleted or modified.

---

## 11. Security Requirements

### 11.1 Authentication

- API authentication via API keys (for service-to-service) and/or JWT tokens (for user-facing clients).
- API keys must be hashed before storage.
- JWT tokens should have short expiry with refresh token support.

### 11.2 Authorization

- Role-based access control (RBAC):
  - `admin`: full access including reconciliation, refunds, audit log viewing.
  - `service`: payment creation, status checking.
  - `readonly`: status checking only.

### 11.3 Transport Security

- HTTPS only in production.
- HSTS headers.
- CORS configured to allow only known client origins.

### 11.4 Input Validation

- All request bodies validated via Pydantic models.
- Amount must be positive integer (in smallest currency unit, e.g., cents).
- Currency must be a valid ISO 4217 code.
- Metadata fields size-limited.

### 11.5 Secrets Management

- Stripe keys in environment variables, never in code or config files committed to git.
- `.env` files in `.gitignore`.
- Support for secrets managers (AWS Secrets Manager, HashiCorp Vault) as future enhancement.

### 11.6 Rate Limiting

- Rate limiting on payment creation endpoints (e.g., 10 requests per minute per API key).
- Rate limiting on webhook endpoint to prevent abuse.
- Return `429 Too Many Requests` with `Retry-After` header.

### 11.7 PCI Compliance Considerations

- The service never handles raw card data. All card input goes directly to Stripe via client-side SDKs.
- This keeps the service in SAQ-A or SAQ-A-EP scope.
- No cardholder data is stored, processed, or transmitted by the backend.

---

## 12. Data Model Overview

### Core Entities

#### `payments`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| external_id | String | Provider-side ID (e.g., Stripe PaymentIntent ID) |
| provider | String | Provider name (e.g., "stripe") |
| status | Enum | pending, processing, succeeded, failed, canceled, refunded, partially_refunded, disputed |
| amount | Integer | Amount in smallest currency unit (cents) |
| currency | String(3) | ISO 4217 currency code |
| customer_id | UUID/String | Internal customer identifier |
| provider_customer_id | String | Provider-side customer ID |
| metadata | JSON | Arbitrary key-value metadata |
| idempotency_key | String | Client-provided idempotency key |
| client_secret | String | Provider client secret for client-side confirmation |
| created_at | Timestamp | Creation time |
| updated_at | Timestamp | Last update time |
| confirmed_at | Timestamp | Confirmation time |

#### `refunds`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| payment_id | UUID | FK to payments |
| external_id | String | Provider-side refund ID |
| amount | Integer | Refund amount in smallest currency unit |
| reason | String | Reason for refund |
| status | Enum | pending, succeeded, failed |
| idempotency_key | String | Idempotency key |
| created_at | Timestamp | Creation time |
| updated_at | Timestamp | Last update time |

#### `webhook_events`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| provider | String | Provider name |
| event_id | String | Provider event ID (unique, for idempotency) |
| event_type | String | Event type (e.g., payment_intent.succeeded) |
| payload | JSON | Raw event payload |
| processed | Boolean | Whether the event has been processed |
| processed_at | Timestamp | Processing time |
| created_at | Timestamp | Receipt time |

#### `idempotency_records`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| key | String | Idempotency key (unique) |
| request_path | String | Request path |
| request_hash | String | Hash of request body |
| response_status | Integer | Cached response status code |
| response_body | JSON | Cached response body |
| expires_at | Timestamp | Expiry time |
| created_at | Timestamp | Creation time |

#### `audit_log`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key (append-only) |
| timestamp | Timestamp | Event time |
| actor_id | String | Who performed the action |
| actor_type | Enum | user, system, webhook, admin |
| action | String | Action performed (e.g., payment.created, refund.initiated) |
| resource_type | String | Type of resource (payment, refund, etc.) |
| resource_id | UUID | ID of the affected resource |
| details | JSON | Additional details |
| ip_address | String | Source IP address |
| outcome | Enum | success, failure |

#### `api_keys`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | String | Human-readable name |
| key_hash | String | Hashed API key |
| key_prefix | String(8) | First 8 chars of key for identification |
| role | Enum | admin, service, readonly |
| is_active | Boolean | Whether the key is active |
| created_at | Timestamp | Creation time |
| last_used_at | Timestamp | Last usage time |
| expires_at | Timestamp | Optional expiry |

---

## 13. API Contract Overview

### Base URL

```
/api/v1
```

### Authentication

All endpoints require authentication via:
- `Authorization: Bearer <jwt_token>` (for user clients)
- `X-API-Key: <api_key>` (for service clients)

### Endpoints

#### Payments

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /payments | Create a new payment intent | service, admin |
| GET | /payments/{payment_id} | Get payment details | service, admin, readonly |
| GET | /payments | List payments (with filters) | admin, readonly |
| POST | /payments/{payment_id}/confirm | Server-side confirm (optional) | service, admin |
| POST | /payments/{payment_id}/cancel | Cancel a payment | service, admin |

#### Refunds

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /payments/{payment_id}/refund | Initiate a refund | admin |
| GET | /payments/{payment_id}/refunds | List refunds for a payment | admin, readonly |
| GET | /refunds/{refund_id} | Get refund details | admin, readonly |

#### Webhooks

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /webhooks/stripe | Stripe webhook endpoint | Stripe signature |

#### Reconciliation

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /admin/reconciliation/run | Trigger reconciliation | admin |
| GET | /admin/reconciliation/reports | List reconciliation reports | admin |
| GET | /admin/reconciliation/reports/{report_id} | Get report details | admin |

#### Health / Info

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | /health | Health check | none |
| GET | /info | Service info/version | none |

### Common Headers

| Header | Description |
|--------|-------------|
| Idempotency-Key | Required for all POST endpoints. Client-generated unique key. |
| Content-Type | `application/json` |
| Authorization | Bearer token or API key |

### Standard Error Response

```json
{
  "error": {
    "code": "PAYMENT_NOT_FOUND",
    "message": "Payment with ID xyz not found.",
    "details": {}
  }
}
```

---

## 14. Webhook Flow

### Stripe Webhook Processing

1. Stripe sends POST to `/api/v1/webhooks/stripe`.
2. Backend reads raw body and `Stripe-Signature` header.
3. Backend verifies signature using `stripe.Webhook.construct_event()` with `STRIPE_WEBHOOK_SECRET`.
4. If verification fails, return `400 Bad Request`.
5. Check if `event.id` exists in `webhook_events` table. If already processed, return `200 OK` (idempotent).
6. Store the event in `webhook_events` table with `processed = false`.
7. Process the event:
   - Map event type to internal handler.
   - Update payment/refund status in database.
   - Create audit log entry.
8. Mark event as `processed = true`.
9. Return `200 OK`.

### Retry Handling

- Stripe retries failed webhook deliveries for up to 3 days.
- The service must handle retries gracefully via idempotent event processing.
- If processing fails, return a non-200 status so Stripe retries.

---

## 15. Reconciliation Design

### Purpose

Detect and flag discrepancies between the internal payment database and the Stripe records.

### Approach

1. Fetch payments from internal database for a given date range.
2. Fetch corresponding charges/payment intents from Stripe API.
3. Compare:
   - Existence: every internal record should have a matching Stripe record and vice versa.
   - Amount: amounts should match.
   - Status: statuses should be consistent.
   - Currency: currencies should match.
4. Generate a report with:
   - Matched records count.
   - Discrepancies (with details).
   - Missing records (internal or Stripe-side).
5. Store the report in the database.
6. Optionally send alerts for critical discrepancies.

### Scheduling

- Can be triggered manually via admin API.
- Can be scheduled as a periodic background job (daily recommended).

---

## 16. Testing Strategy

### Unit Tests

- Test all service-layer business logic in isolation.
- Mock the provider interface for unit tests.
- Test idempotency logic.
- Test validation logic.
- Test reconciliation logic.

### Integration Tests

- Test the full API flow with a test database.
- Test Stripe integration using Stripe test mode and test card numbers.
- Test webhook handling with simulated Stripe events (using `stripe.Webhook.construct_event` with test payloads).
- Test database migrations.

### End-to-End Tests

- Test complete payment flow: create -> confirm -> webhook -> status check.
- Test refund flow: create payment -> confirm -> refund -> webhook -> status check.
- Test error scenarios: failed payments, invalid requests, duplicate idempotency keys.

### Security Tests

- Test authentication: unauthenticated requests rejected.
- Test authorization: role-based access enforced.
- Test rate limiting: excessive requests throttled.
- Test webhook signature verification: invalid signatures rejected.

### Test Infrastructure

- Use pytest as the test runner.
- Use pytest-asyncio for async test support.
- Use factory_boy for test data generation.
- Use httpx.AsyncClient for API testing.
- Use Stripe test mode for integration tests.

---

## 17. Client Integration Guide

### Angular Integration

1. Backend creates a PaymentIntent via `/api/v1/payments`.
2. Backend returns `client_secret` to Angular app.
3. Angular loads Stripe.js (`@stripe/stripe-js`).
4. Angular calls `stripe.confirmPayment({ clientSecret, ... })` with payment element.
5. Stripe handles 3D Secure / SCA if required.
6. Angular receives confirmation result from Stripe.
7. Angular can poll `/api/v1/payments/{payment_id}` for final status, or rely on webhooks updating the backend.

### Flutter Integration

1. Backend creates a PaymentIntent via `/api/v1/payments`.
2. Backend returns `client_secret` to Flutter app.
3. Flutter initializes `flutter_stripe` with publishable key.
4. Flutter calls `Stripe.instance.confirmPayment(clientSecret, ...)`.
5. Stripe handles 3D Secure / SCA if required.
6. Flutter receives confirmation result from Stripe.
7. Flutter can poll `/api/v1/payments/{payment_id}` for final status, or rely on webhooks updating the backend.

### Generic API Client Integration

1. Client authenticates via API key or JWT.
2. Client sends `POST /api/v1/payments` with amount, currency, metadata, and `Idempotency-Key` header.
3. Client receives `{ payment_id, client_secret, status }`.
4. Client uses `client_secret` with appropriate Stripe SDK to confirm payment on client side.
5. Client polls `GET /api/v1/payments/{payment_id}` for status updates.

### Server-to-Server Integration

1. Service authenticates via API key.
2. Service creates payment via `POST /api/v1/payments` with `Idempotency-Key`.
3. For server-to-server flows (no client-side confirmation needed), the service can use `POST /api/v1/payments/{payment_id}/confirm` for server-side confirmation with a previously saved payment method.
4. Service receives webhook notifications or polls for status.

---

## 18. Project Directory Structure (Target)

```
paygateway/
  README.md
  system-vision.md
  specs/
    payment-gateway-core/
      spec.md
      plan.md
      tasks.md
      data-model.md
      api-contract.md
      security.md
      provider-interface.md
      stripe-provider.md
      webhook-flow.md
      reconciliation.md
      testing-strategy.md
      client-integration.md
      assumptions.md
      risks.md
  src/
    paygateway/
      __init__.py
      main.py                    # FastAPI app entry point
      config.py                  # Configuration (env vars, settings)
      dependencies.py            # FastAPI dependency injection
      models/                    # SQLAlchemy models
        __init__.py
        payment.py
        refund.py
        webhook_event.py
        idempotency.py
        audit_log.py
        api_key.py
      schemas/                   # Pydantic request/response schemas
        __init__.py
        payment.py
        refund.py
        webhook.py
        common.py
      routes/                    # FastAPI route handlers
        __init__.py
        payments.py
        refunds.py
        webhooks.py
        reconciliation.py
        health.py
      services/                  # Business logic
        __init__.py
        payment_service.py
        refund_service.py
        webhook_service.py
        reconciliation_service.py
        idempotency_service.py
        audit_service.py
      providers/                 # Payment provider abstraction
        __init__.py
        base.py                  # Abstract provider interface
        stripe_provider.py       # Stripe implementation
      middleware/                # FastAPI middleware
        __init__.py
        authentication.py
        rate_limiting.py
        idempotency.py
      db/                        # Database utilities
        __init__.py
        session.py
        base.py
      migrations/                # Alembic migrations
        env.py
        versions/
  tests/
    __init__.py
    conftest.py
    unit/
    integration/
    e2e/
  alembic.ini
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  Dockerfile
  docker-compose.yml
  .env.example
  .gitignore
```

---

## 19. Assumptions

These are assumptions made based on best professional judgment. They are documented here and will also be recorded in `/specs/payment-gateway-core/assumptions.md`.

1. **Empty Repository:** The repository is empty (initial commit only). Python + FastAPI is chosen as the backend stack.
2. **Single Service:** The payment gateway is a single deployable service (not microservices) for the initial version.
3. **Supabase (PostgreSQL):** Supabase (managed PostgreSQL) is used for both local development and production. Use the direct connection (port 5432) with `asyncpg` — avoid PgBouncer (port 6432) in transaction mode as it conflicts with prepared statements. SSL is required (`sslmode=require`). SQLite is not used.
4. **No Existing Auth System:** The service implements its own API key and JWT authentication. If an external auth system exists in the broader ecosystem, it can be integrated later.
5. **Stripe PaymentIntents:** The primary Stripe flow uses PaymentIntents (not legacy Charges API).
6. **Currency Handling:** Amounts are always in the smallest currency unit (e.g., cents for USD). The backend does not perform currency conversion.
7. **Single Currency Per Payment:** Each payment is in a single currency. Multi-currency support within a single payment is not in scope.
8. **No Subscription Management:** Recurring payments/subscriptions are out of scope for the initial version. Can be added later.
9. **No Invoice Generation:** Invoice/receipt generation is out of scope. Can be added later.
10. **Webhook-Driven Status Updates:** Payment status is primarily updated via webhooks. Polling is supported as a fallback.
11. **Idempotency TTL:** Default idempotency key TTL is 24 hours.
12. **Background Jobs:** Reconciliation runs as a background job. For the initial version, a simple async task runner (e.g., ARQ with Redis, or a simple in-process scheduler) is sufficient. Full Celery setup is deferred unless needed.
13. **Deployment:** Docker-based deployment. Specific cloud provider (AWS, GCP, Azure) is not prescribed; the service should be cloud-agnostic.
14. **Database Hosting:** Supabase is the managed database provider. The application connects to Supabase PostgreSQL via the direct connection string with SSL. Supabase handles backups, scaling, and database management. Environment variables: `SUPABASE_DB_URL` (direct PostgreSQL connection string), `SUPABASE_URL` (project API URL), `SUPABASE_ANON_KEY` (public anon key, if needed for future Supabase features).

---

## 20. Risks

These will also be documented in `/specs/payment-gateway-core/risks.md`.

1. **Stripe API Changes:** Stripe may deprecate APIs or change behavior. Mitigation: Pin Stripe API version, monitor Stripe changelog.
2. **Webhook Reliability:** Webhooks can be delayed or fail. Mitigation: Support polling as fallback, implement reconciliation.
3. **Idempotency Key Collisions:** Clients may reuse idempotency keys incorrectly. Mitigation: Document requirements clearly, validate request hash matches.
4. **Concurrency Issues:** Multiple requests with same idempotency key arriving simultaneously. Mitigation: Use database-level unique constraints and row locking.
5. **Security Vulnerabilities:** Payment systems are high-value targets. Mitigation: Security review, penetration testing, dependency scanning, minimal attack surface.
6. **Data Loss:** Payment data is critical. Mitigation: Supabase automatic backups, point-in-time recovery, transaction logging, audit trail.
7. **Provider Lock-in:** While provider abstraction exists, Stripe-specific features may leak into business logic. Mitigation: Code reviews, clear interface boundaries, integration tests against the abstract interface.

---

## 21. Next Steps After This Phase

After the specification phase is complete (all `/specs/payment-gateway-core/` files created), the implementation phase should be executed as follows:

1. Start a new Claude Code session (can use a cheaper mode/model).
2. Reference this `system-vision.md` as the source of truth.
3. Read all files in `/specs/payment-gateway-core/`.
4. Execute the implementation tasks in the order defined in `tasks.md`.
5. Follow the plan in `plan.md`.
6. After implementation, run the test suite.
7. Review the implementation against the specification.
8. Create a PR or commit with the implementation.

The implementation session should not re-do specification work. It should treat the specs as requirements and implement them.
