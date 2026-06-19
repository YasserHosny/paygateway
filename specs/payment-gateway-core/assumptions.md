# Payment Gateway Core Service — Assumptions

This document records assumptions made during the specification phase. Each assumption represents a professional recommendation where the requirement was ambiguous or unspecified.

## Architecture Assumptions

### A1: Empty Repository — Python + FastAPI

**Assumption:** The repository is empty (initial commit with README only). Python + FastAPI is the recommended backend stack.

**Rationale:** FastAPI provides async support, automatic OpenAPI docs, Pydantic validation, and is well-suited for API-first payment services. If a future run finds an existing stack, it should adapt.

### A2: Single Deployable Service

**Assumption:** The payment gateway is a single deployable service, not a microservices architecture.

**Rationale:** For v1, a monolith is simpler to develop, deploy, and debug. The internal architecture (service layer, provider abstraction) supports extraction into microservices later if needed.

### A3: PostgreSQL as Primary Database

**Assumption:** PostgreSQL (Supabase-managed) is used for both local development and production. SQLite is not used.

**Rationale:** Using the same remote Supabase database for local development eliminates environment drift between dev and production. JSONB, transactions, and index behavior are identical across environments.

### A4: Redis for Rate Limiting and Caching

**Assumption:** Redis is used for rate limiting state and optional caching. An in-memory fallback exists for single-instance development.

**Rationale:** Rate limiting requires fast, shared state. Redis is the standard solution. In-memory fallback avoids requiring Redis for local development.

## Payment Flow Assumptions

### A5: Stripe PaymentIntents API

**Assumption:** The primary Stripe flow uses the PaymentIntents API, not the legacy Charges API.

**Rationale:** PaymentIntents is Stripe's recommended API. It supports SCA/3D Secure, handles complex payment flows, and is required for European payments.

### A6: Client-Side Confirmation as Default

**Assumption:** The default flow is client-side confirmation where the client uses Stripe.js or Flutter Stripe SDK to confirm the payment.

**Rationale:** This is the most common pattern for web and mobile apps. Server-side confirmation is supported as an alternative for saved payment methods.

### A7: Single Currency Per Payment

**Assumption:** Each payment is in a single currency. Multi-currency conversion within a single payment is out of scope.

**Rationale:** Currency conversion adds significant complexity (exchange rates, rounding, settlement). Can be added in a future version.

### A8: Amounts in Smallest Currency Unit

**Assumption:** All amounts are integers in the smallest currency unit (e.g., cents for USD, pence for GBP).

**Rationale:** Matches Stripe's API convention. Avoids floating-point precision issues.

## Authentication Assumptions

### A9: Self-Contained Authentication

**Assumption:** The service implements its own API key and JWT validation. It does not depend on an external identity provider for v1.

**Rationale:** Makes the service self-contained and deployable independently. Integration with external auth (OAuth2, OIDC, Auth0, etc.) can be added later.

### A10: JWT Validation Only

**Assumption:** The service validates JWTs but does not issue them. Token issuance is the responsibility of the consuming application's auth system.

**Rationale:** The payment gateway should not be an identity provider. It trusts tokens from authorized issuers.

## Operational Assumptions

### A11: Idempotency Key TTL — 24 Hours

**Assumption:** Idempotency keys expire after 24 hours.

**Rationale:** Matches Stripe's own idempotency key TTL. Long enough for retries, short enough to prevent stale data accumulation.

### A12: Webhook Event Retention — 90 Days

**Assumption:** Webhook events are retained for 90 days before being eligible for archival.

**Rationale:** 90 days provides sufficient time for dispute resolution and debugging. Matches Stripe's event retention period.

### A13: Docker-Based Deployment

**Assumption:** The service is deployed via Docker containers. No specific cloud provider is prescribed.

**Rationale:** Docker is cloud-agnostic and supports all major deployment platforms.

### A14: Background Jobs via ARQ or In-Process

**Assumption:** For v1, background jobs (reconciliation, cleanup) use a lightweight solution (ARQ with Redis, or FastAPI BackgroundTasks). Full Celery setup is deferred.

**Rationale:** Celery adds operational complexity. ARQ or in-process tasks are sufficient for the initial workload.

## Scope Assumptions

### A15: No Subscriptions in v1

**Assumption:** Recurring payments and subscription management are out of scope for v1.

**Rationale:** Subscriptions require additional Stripe objects (Subscriptions, Plans, Prices), billing cycle management, and proration logic. These are better addressed as a separate module.

### A16: No Invoice Generation in v1

**Assumption:** Invoice and receipt generation are out of scope for v1.

**Rationale:** Invoice generation is a separate concern that can be handled by a different service or added as a module later.

### A17: No Marketplace Payments in v1

**Assumption:** Stripe Connect and marketplace payment splitting are out of scope.

**Rationale:** Connect adds significant complexity (connected accounts, platform fees, transfers). Can be added as a separate module.

### A18: Manual Reconciliation Resolution

**Assumption:** Reconciliation flags discrepancies but does not auto-correct them. Resolution is manual.

**Rationale:** Auto-correction of financial records is risky. Manual review ensures correctness and accountability.
