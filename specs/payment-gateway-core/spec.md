# Payment Gateway Core Service — Specification

## 1. Overview

The Payment Gateway Core Service is a production-grade, reusable payment orchestration layer that sits between client applications and payment providers. It centralizes all payment logic, ensuring that no client application (Angular, Flutter, desktop, or third-party) directly handles sensitive payment operations.

Stripe is the first and default payment provider. The architecture supports adding additional providers without modifying core business logic.

## 2. System Context

```
+-------------------+     +-------------------+     +-------------------+
| Angular Web App   |     | Flutter Mobile App |     | Desktop / API     |
+--------+----------+     +--------+----------+     +--------+----------+
         |                         |                          |
         |    REST API (HTTPS)     |                          |
         +------------+------------+--------------------------+
                      |
         +------------v-------------+
         |  Payment Gateway Core    |
         |  Service (FastAPI)       |
         +---+--------+--------+---+
             |        |        |
     +-------v--+ +---v----+ +v----------+
     | PostgreSQL| | Redis  | | Stripe API|
     +----------+ +--------+ +-----------+
```

## 3. Functional Requirements

### FR-1: Payment Initiation
- Accept payment requests with amount (smallest currency unit), currency (ISO 4217), customer reference, metadata, and idempotency key.
- Create a PaymentIntent via the configured provider (Stripe).
- Return an internal payment ID, client secret, and initial status to the caller.
- Validate all inputs before calling the provider.

### FR-2: Payment Confirmation
- Client-side confirmation via Stripe SDK using the returned client secret.
- Server-side confirmation endpoint for saved payment methods (server-to-server flows).
- Status updated primarily via webhooks; polling endpoint available as fallback.

### FR-3: Payment Status Tracking
- Query single payment by ID.
- List payments with filtering: status, customer, date range, currency.
- Pagination support (cursor-based preferred, offset acceptable for v1).

### FR-4: Payment Cancellation
- Cancel a pending/uncaptured payment.
- Idempotency key required.
- Audit log entry on cancellation.

### FR-5: Refunds
- Full refund: refund the entire payment amount.
- Partial refund: refund a specified amount (must not exceed remaining refundable amount).
- Reason field (optional but recommended).
- Idempotency key required.
- Refund status tracked via webhooks.
- Multiple partial refunds allowed up to the original amount.

### FR-6: Webhook Handling
- Receive and verify provider webhook events.
- Process events idempotently (deduplicate by event ID).
- Update internal payment/refund state based on events.
- Handle: `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`, `charge.refunded`, `charge.dispute.created`, `charge.dispute.closed`.
- Return 200 for successfully received events (even if already processed).
- Return non-200 for events that fail processing (triggers provider retry).

### FR-7: Idempotency
- All mutating endpoints require `Idempotency-Key` header.
- Duplicate requests with same key and matching request body return cached response.
- Mismatched request body with same key returns 422 error.
- Keys expire after 24 hours (configurable).
- Concurrent duplicate requests handled via database locking.

### FR-8: Audit Logging
- Append-only log of all payment-related actions.
- Fields: timestamp, actor (ID + type), action, resource (type + ID), details (JSON), IP, outcome.
- Covers: payment creation, confirmation, cancellation, refund initiation, status changes, webhook processing, reconciliation runs.
- Audit records are immutable — no update or delete operations.

### FR-9: Reconciliation
- Compare internal records against Stripe records for a date range.
- Detect: missing records, amount mismatches, status mismatches, currency mismatches.
- Generate reconciliation reports stored in database.
- Triggerable via admin API or scheduled background job.

### FR-10: Health and Info
- `GET /health` returns service health (database connectivity, provider reachability).
- `GET /info` returns service version, environment, uptime.
- No authentication required for these endpoints.

## 4. Non-Functional Requirements

### NFR-1: Performance
- Payment creation: < 2 seconds end-to-end (including Stripe call).
- Status query: < 200ms.
- Webhook processing: < 1 second per event.
- Support 100+ concurrent payment requests.

### NFR-2: Availability
- Target 99.9% uptime.
- Graceful degradation if Stripe is unreachable (queue and retry where possible).

### NFR-3: Security
- See `security.md` for full details.
- HTTPS only in production.
- No raw card data handled by the service.
- API authentication required for all endpoints except health/info and webhooks (which use signature verification).

### NFR-4: Observability
- Structured logging (JSON format).
- Request correlation IDs.
- Key metrics: payment counts by status, latency histograms, error rates.
- Health check endpoint for monitoring systems.

### NFR-5: Extensibility
- Provider abstraction allows adding new providers without core changes.
- API versioning (`/api/v1/`) supports future breaking changes.
- Feature flags for gradual rollout of new capabilities.

## 5. Out of Scope (v1)

- Subscription/recurring billing management.
- Invoice/receipt generation.
- Multi-currency conversion.
- Marketplace/Connect payments (Stripe Connect).
- Payout management.
- Customer portal UI.
- Email notifications.

These may be added in future versions.

## 6. Glossary

| Term | Definition |
|------|-----------|
| PaymentIntent | Stripe object representing a payment lifecycle from creation to completion |
| Client Secret | Token returned by Stripe that allows client-side SDKs to confirm a payment without exposing secret keys |
| Idempotency Key | Client-generated unique string ensuring a request is processed at most once |
| Webhook | HTTP callback from Stripe notifying the service of asynchronous events |
| Reconciliation | Process of comparing internal payment records against provider records to detect discrepancies |
| SAQ-A | PCI DSS self-assessment questionnaire for merchants who fully outsource cardholder data handling |
| Provider Adapter | Implementation of the abstract payment provider interface for a specific provider (e.g., Stripe) |
