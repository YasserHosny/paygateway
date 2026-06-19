# API Reference

Base URL: `https://your-domain.com`  
Interactive docs: `GET /docs` (Swagger UI) · `GET /redoc` (ReDoc)

All API endpoints are prefixed with `/api/v1` except health endpoints.

---

## Authentication

All `/api/v1/*` endpoints require one of:

**API Key** (preferred for server-to-server):
```
X-API-Key: pgw_<your_api_key>
```

**JWT Bearer** (for session-based access):
```
Authorization: Bearer <jwt_token>
```

**Roles:**
- `admin` — full access (create, confirm, cancel, refund, reconcile)
- `service` — create, confirm, cancel payments
- `readonly` — GET endpoints only

---

## Idempotency

All `POST` requests require an `Idempotency-Key` header:
```
Idempotency-Key: <unique-string-up-to-255-chars>
```
Replaying the same key within 24 hours returns the original response without re-executing the operation. Use UUIDs or `<operation>-<order-id>-<timestamp>` patterns.

---

## Common Response Formats

### Success
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  ...
}
```

### Error
```json
{
  "detail": {
    "error": {
      "code": "PAYMENT_NOT_FOUND",
      "message": "Payment not found",
      "details": {}
    }
  }
}
```

### Paginated List
```json
{
  "data": [...],
  "pagination": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

---

## Health

### `GET /health`
Database connectivity check. Used by load balancers.

**No authentication required.**

**Response 200:**
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok"
  },
  "timestamp": "2026-06-19T15:34:29.982399Z"
}
```
`status` is `"degraded"` if any check fails.

---

### `GET /info`
Returns environment name.

**Response 200:**
```json
{
  "environment": "production"
}
```

---

## Payments

### `POST /api/v1/payments`
Create a payment intent with Stripe.

**Roles:** `admin`, `service`  
**Headers:** `Idempotency-Key` required

**Request body:**
```json
{
  "amount": 2500,
  "currency": "USD",
  "customer_id": "cust_abc123",
  "description": "Order #1001",
  "metadata": {
    "order_id": "1001",
    "channel": "web"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount` | integer | yes | Amount in smallest currency unit (cents). Min 1, max 99 999 999 |
| `currency` | string | yes | ISO 4217, 3-letter (e.g. `USD`, `EUR`) |
| `customer_id` | string | no | Your internal customer identifier (max 255 chars) |
| `description` | string | no | Human-readable description (max 500 chars) |
| `metadata` | object | no | Key-value pairs. Max 20 keys, 40-char keys, 500-char values |

**Response 201:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "external_id": "pi_3Tk4Y3DTpg7yoNvm3RDbdsdQ",
  "provider": "stripe",
  "status": "pending",
  "amount": 2500,
  "currency": "USD",
  "customer_id": "cust_abc123",
  "description": "Order #1001",
  "client_secret": "pi_3Tk4Y3..._secret_...",
  "metadata": { "order_id": "1001" },
  "created_at": "2026-06-19T15:34:29Z",
  "updated_at": "2026-06-19T15:34:29Z",
  "confirmed_at": null,
  "canceled_at": null,
  "failure_code": null,
  "failure_message": null,
  "refunded_amount": 0
}
```

> **Important:** Pass `client_secret` to your frontend Stripe.js to collect card details client-side. Never expose your Stripe secret key to the frontend.

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 422 | `IDEMPOTENCY_KEY_MISSING` | Header not provided |
| 502 | `PROVIDER_ERROR` | Stripe returned an error |

---

### `GET /api/v1/payments/{payment_id}`
Retrieve a single payment by internal UUID.

**Roles:** `admin`, `service`, `readonly`

> Note: `client_secret` is redacted (`null`) on GET responses.

**Response 200:** Same shape as create response.

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `PAYMENT_NOT_FOUND` | No payment with that ID |

---

### `GET /api/v1/payments`
List payments with optional filters.

**Roles:** `admin`, `readonly`

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status (`pending`, `succeeded`, `canceled`, etc.) |
| `customer_id` | string | Filter by your customer identifier |
| `currency` | string | Filter by currency (e.g. `USD`) |
| `created_after` | ISO datetime | Filter payments created after this timestamp |
| `created_before` | ISO datetime | Filter payments created before this timestamp |
| `limit` | integer | Results per page. Default 20, max 100 |
| `offset` | integer | Pagination offset. Default 0 |

**Response 200:** Paginated list of payment objects.

---

### `POST /api/v1/payments/{payment_id}/confirm`
Confirm a pending payment with a Stripe payment method ID.

**Roles:** `admin`, `service`  
**Headers:** `Idempotency-Key` required

**Request body:**
```json
{
  "payment_method_id": "pm_card_visa"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payment_method_id` | string | yes | Stripe payment method ID (from Stripe.js or test shorthand) |

**Response 200:** Updated payment object. Status will be `succeeded` on success.

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `PAYMENT_NOT_FOUND` | Payment does not exist |
| 502 | `PROVIDER_ERROR` | Stripe rejected confirmation |

---

### `POST /api/v1/payments/{payment_id}/cancel`
Cancel a payment that has not yet been captured.

**Roles:** `admin`, `service`  
**Headers:** `Idempotency-Key` required

**Request body (optional):**
```json
{
  "reason": "Customer changed their mind"
}
```

**Response 200:** Updated payment with `status: "canceled"` and `canceled_at` timestamp.

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `PAYMENT_NOT_FOUND` | Payment does not exist |
| 409 | `PAYMENT_NOT_CANCELABLE` | Payment is in a non-cancelable state (already succeeded or canceled) |
| 502 | `PROVIDER_ERROR` | Stripe returned an error |

---

## Refunds

### `POST /api/v1/payments/{payment_id}/refund`
Issue a full or partial refund for a succeeded payment.

**Roles:** `admin`  
**Headers:** `Idempotency-Key` required

**Request body (optional):**
```json
{
  "amount": 1000,
  "reason": "customer_request"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount` | integer | no | Amount to refund in cents. Omit for full refund |
| `reason` | string | no | One of: `customer_request`, `duplicate`, `fraudulent` |

**Response 201:**
```json
{
  "id": "455c194d-9874-4572-a874-ff7ee3ada87f",
  "payment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "external_id": "re_3Tk4Y3DTpg7yoNvm3aucgMor",
  "amount": 1000,
  "reason": "customer_request",
  "status": "succeeded",
  "failure_reason": null,
  "created_at": "2026-06-19T16:00:00Z",
  "updated_at": "2026-06-19T16:00:00Z"
}
```

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `PAYMENT_NOT_FOUND` | Payment does not exist |
| 409 | `PAYMENT_NOT_REFUNDABLE` | Payment is not in a refundable state |
| 409 | `REFUND_EXCEEDS_AMOUNT` | Refund amount exceeds remaining refundable balance |
| 502 | `PROVIDER_ERROR` | Stripe returned an error |

---

### `GET /api/v1/refunds/{refund_id}`
Retrieve a single refund by UUID.

**Roles:** `admin`, `readonly`

**Response 200:** Refund object.

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `REFUND_NOT_FOUND` | No refund with that ID |

---

### `GET /api/v1/payments/{payment_id}/refunds`
List all refunds for a payment.

**Roles:** `admin`, `readonly`

**Query parameters:** `limit` (default 20, max 100), `offset` (default 0)

**Response 200:** Paginated list of refund objects.

---

## Webhooks

### `POST /api/v1/webhooks/stripe`
Stripe webhook receiver. Configure this URL in your Stripe dashboard.

**No API Key required** — Stripe signature verified via `STRIPE_WEBHOOK_SECRET`.

**Headers Stripe sends:**
```
Stripe-Signature: t=...,v1=...
```

**Response 200:**
```json
{ "received": true }
```

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 400 | `INVALID_SIGNATURE` | Webhook signature verification failed |

**Events processed:**
- `payment_intent.succeeded` → updates payment to `succeeded`
- `payment_intent.payment_failed` → updates payment to `failed` with error details
- `payment_intent.canceled` → updates payment to `canceled`
- `charge.refund.updated` → syncs refund status

---

## Reconciliation

### `POST /api/v1/admin/reconciliation/run`
Trigger a reconciliation run comparing internal DB state with Stripe.

**Roles:** `admin`

**Request body:**
```json
{
  "date_range_start": "2026-06-01T00:00:00Z",
  "date_range_end": "2026-06-19T23:59:59Z"
}
```

**Response 202:**
```json
{
  "report_id": "7a2e8f91-...",
  "status": "pending"
}
```

---

### `GET /api/v1/admin/reconciliation/reports`
List reconciliation reports.

**Roles:** `admin`

**Query parameters:** `limit` (default 20, max 100), `offset` (default 0)

---

### `GET /api/v1/admin/reconciliation/reports/{report_id}`
Get a specific reconciliation report.

**Roles:** `admin`

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 404 | `REPORT_NOT_FOUND` | No report with that ID |

---

## Payment Statuses

| Status | Description |
|--------|-------------|
| `pending` | Created, awaiting confirmation |
| `processing` | Confirmed, Stripe processing |
| `succeeded` | Charge completed successfully |
| `requires_action` | 3DS or redirect required from customer |
| `canceled` | Cancelled before capture |
| `failed` | Charge failed (see `failure_code`) |
| `partially_refunded` | Some amount refunded, not all |
| `refunded` | Fully refunded |

## Refund Statuses

| Status | Description |
|--------|-------------|
| `pending` | Queued with Stripe |
| `succeeded` | Refund completed |
| `failed` | Refund failed (see `failure_reason`) |

## Rate Limits

| Endpoint prefix | Requests / 60 s (per API key or IP) |
|----------------|--------------------------------------|
| `/api/v1/payments` | 30 |
| `/api/v1/refunds` | 10 |
| `/api/v1/admin/reconciliation` | 5 |
| `/api/v1/webhooks` | 300 |
| `/health`, `/info` | 60 |
| All others | 120 |

Rate limit headers returned on every response:
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 29
X-RateLimit-Reset: 1750345869
```
On limit breach: `HTTP 429` with `Retry-After` header.
