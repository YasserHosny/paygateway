# Payment Gateway — Overview

## What Is It?

PayGateway is a self-hosted, API-first payment processing backend built for businesses that need full control over their payment infrastructure. It sits between your frontend applications (web, mobile) and Stripe, adding a secure, auditable, and idempotent layer that you own completely.

## Why Build Your Own Gateway Layer?

| Concern | Direct Stripe Integration | PayGateway |
|---------|--------------------------|------------|
| Secret key exposure | Risk if not careful | Keys never leave the server |
| Audit trail | Stripe dashboard only | Full audit log in your DB |
| Multi-client support | Share one key or manage many | API key per client, role-based |
| Idempotency | Must implement yourself | Built-in via `Idempotency-Key` header |
| Reconciliation | Manual | Automated nightly jobs |
| Portability | Stripe-locked frontend | Provider-agnostic API contract |

## Core Capabilities

### Payment Lifecycle
- **Create** a payment intent with amount, currency, and metadata
- **Confirm** with a Stripe payment method token from the client
- **Cancel** uncaptured payments before they are charged
- **Refund** fully or partially after a successful charge

### Security & Access Control
- **API Key authentication** — SHA-256 hashed, salted, prefix-indexed
- **JWT authentication** — for short-lived session tokens
- **Role-based access** — `admin`, `service`, `readonly` roles
- **Rate limiting** — per-key sliding window (configurable per endpoint)
- **Idempotency** — replay-safe POST operations via unique keys

### Observability
- **Audit log** — every state change recorded with actor, IP, timestamp
- **Correlation IDs** — every request tagged with `X-Correlation-ID`
- **Structured logging** — JSON-ready log output
- **Health endpoint** — DB connectivity check for load balancer probes

### Reconciliation
- **Automated nightly jobs** — compare internal DB state vs Stripe
- **On-demand runs** — trigger reconciliation for any date range via API
- **Reports** — stored in DB, queryable via API

### Webhook Processing
- **Stripe signature verification** — HMAC-SHA256 on every inbound event
- **Idempotent processing** — duplicate events handled safely
- **Payment state sync** — `payment_intent.*` events update DB automatically

## Supported Payment Flows

```
Client App                   PayGateway API              Stripe
    │                               │                       │
    │── POST /payments ────────────>│── create PI ─────────>│
    │<─ { id, client_secret } ──────│<─ PI created ─────────│
    │                               │                       │
    │  [collect card via Stripe.js] │                       │
    │                               │                       │
    │── POST /payments/{id}/confirm>│── confirm PI ────────>│
    │<─ { status: "succeeded" } ────│<─ PI succeeded ───────│
    │                               │                       │
    │── POST /payments/{id}/refund >│── create refund ─────>│
    │<─ { status: "succeeded" } ────│<─ refund created ─────│
```

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────┐
│                     PayGateway API                       │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐  │
│  │ Payments │  │ Refunds  │  │Webhooks│  │Reconcile │  │
│  └────┬─────┘  └────┬─────┘  └───┬────┘  └────┬─────┘  │
│       │              │            │             │         │
│  ┌────▼──────────────▼────────────▼─────────────▼─────┐ │
│  │              Service Layer                          │ │
│  │  payment_service  refund_service  webhook_service   │ │
│  └────────────────────────┬────────────────────────────┘ │
│                           │                              │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │              Provider Abstraction                   │ │
│  │                  StripeProvider                     │ │
│  └────────────────────────┬────────────────────────────┘ │
└───────────────────────────│─────────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │   Stripe    │
                     │    API      │
                     └─────────────┘
          ┌──────────────────────────────────┐
          │       Supabase / PostgreSQL       │
          │  payments  refunds  api_keys      │
          │  audit_log  reconciliation_reports│
          └──────────────────────────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12 |
| Framework | FastAPI (async) |
| Database | PostgreSQL via Supabase |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Payment Provider | Stripe SDK 15.x |
| Containerization | Docker + Docker Compose |
| Testing | pytest-asyncio |

## Environments

| Environment | Purpose |
|-------------|---------|
| `development` | Local development, scheduler disabled |
| `staging` | Pre-production testing with Stripe test keys |
| `production` | Live traffic, real Stripe keys |
