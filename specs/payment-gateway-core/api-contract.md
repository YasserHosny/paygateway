# Payment Gateway Core Service — API Contract

## 1. Base Configuration

- **Base path:** `/api/v1`
- **Content-Type:** `application/json`
- **Character encoding:** UTF-8
- **Date format:** ISO 8601 (`2026-06-16T15:30:00Z`)
- **Amount format:** Integer in smallest currency unit (e.g., 1000 = $10.00 USD)
- **Currency format:** ISO 4217 uppercase (e.g., `USD`, `EUR`, `GBP`)
- **ID format:** UUID v4

## 2. Authentication

All endpoints except `/health`, `/info`, and `/webhooks/*` require authentication.

### API Key Authentication
```
X-API-Key: pgw_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456
```

### JWT Authentication
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

The service checks `X-API-Key` first, then `Authorization` header. If neither is present, returns 401.

## 3. Common Headers

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| Content-Type | Yes (POST/PUT) | Must be `application/json` |
| X-API-Key | Conditional | API key authentication |
| Authorization | Conditional | Bearer token authentication |
| Idempotency-Key | Yes (POST) | Unique key for idempotent operations |
| X-Request-ID | No | Client-provided request correlation ID |

### Response Headers

| Header | Description |
|--------|-------------|
| X-Request-ID | Request correlation ID (echoed or generated) |
| X-RateLimit-Limit | Max requests per window |
| X-RateLimit-Remaining | Remaining requests in window |
| X-RateLimit-Reset | Window reset time (Unix timestamp) |
| Retry-After | Seconds to wait (on 429) |

## 4. Standard Error Response

All errors follow this structure:

```json
{
  "error": {
    "code": "PAYMENT_NOT_FOUND",
    "message": "Payment with the specified ID was not found.",
    "details": {}
  }
}
```

### Error Codes

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | INVALID_REQUEST | Request body validation failed |
| 400 | INVALID_AMOUNT | Amount must be a positive integer |
| 400 | INVALID_CURRENCY | Currency is not a valid ISO 4217 code |
| 401 | UNAUTHORIZED | Missing or invalid authentication |
| 403 | FORBIDDEN | Insufficient role/permissions |
| 404 | PAYMENT_NOT_FOUND | Payment ID does not exist |
| 404 | REFUND_NOT_FOUND | Refund ID does not exist |
| 409 | PAYMENT_NOT_REFUNDABLE | Payment is not in a refundable state |
| 409 | REFUND_EXCEEDS_AMOUNT | Refund amount exceeds remaining refundable amount |
| 409 | PAYMENT_NOT_CANCELABLE | Payment cannot be canceled in current state |
| 422 | IDEMPOTENCY_KEY_MISMATCH | Same key used with different request body |
| 422 | IDEMPOTENCY_KEY_MISSING | POST request without Idempotency-Key header |
| 429 | RATE_LIMITED | Too many requests |
| 500 | INTERNAL_ERROR | Unexpected server error |
| 502 | PROVIDER_ERROR | Payment provider returned an error |
| 503 | PROVIDER_UNAVAILABLE | Payment provider is unreachable |

## 5. Endpoints

### 5.1 Health and Info

#### `GET /health`

No authentication required.

**Response 200:**
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "stripe": "ok"
  },
  "timestamp": "2026-06-16T15:30:00Z"
}
```

#### `GET /info`

No authentication required.

**Response 200:**
```json
{
  "service": "payment-gateway-core",
  "version": "1.0.0",
  "environment": "production"
}
```

---

### 5.2 Payments

#### `POST /api/v1/payments`

Create a new payment intent.

**Required role:** `service`, `admin`

**Request:**
```json
{
  "amount": 5000,
  "currency": "usd",
  "customer_id": "user_abc123",
  "description": "Order #12345",
  "metadata": {
    "order_id": "12345",
    "product": "premium_plan"
  }
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| amount | integer | Yes | > 0, max 99999999 (provider limit) |
| currency | string | Yes | 3-letter ISO 4217, lowercase accepted |
| customer_id | string | No | Max 255 chars |
| description | string | No | Max 500 chars |
| metadata | object | No | Max 20 keys, key max 40 chars, value max 500 chars |

**Response 201:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "pi_3ABC123DEF456",
  "provider": "stripe",
  "status": "pending",
  "amount": 5000,
  "currency": "USD",
  "customer_id": "user_abc123",
  "description": "Order #12345",
  "client_secret": "pi_3ABC123DEF456_secret_xyz",
  "metadata": {
    "order_id": "12345",
    "product": "premium_plan"
  },
  "created_at": "2026-06-16T15:30:00Z",
  "updated_at": "2026-06-16T15:30:00Z",
  "confirmed_at": null,
  "canceled_at": null
}
```

---

#### `GET /api/v1/payments/{payment_id}`

Get payment details by ID.

**Required role:** `service`, `admin`, `readonly`

**Response 200:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "pi_3ABC123DEF456",
  "provider": "stripe",
  "status": "succeeded",
  "amount": 5000,
  "currency": "USD",
  "customer_id": "user_abc123",
  "description": "Order #12345",
  "client_secret": null,
  "metadata": {},
  "created_at": "2026-06-16T15:30:00Z",
  "updated_at": "2026-06-16T15:31:00Z",
  "confirmed_at": "2026-06-16T15:31:00Z",
  "canceled_at": null,
  "failure_code": null,
  "failure_message": null,
  "refunded_amount": 0
}
```

Note: `client_secret` is only returned in the creation response and nulled afterward for security.

---

#### `GET /api/v1/payments`

List payments with optional filters.

**Required role:** `admin`, `readonly`

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status |
| customer_id | string | Filter by customer |
| currency | string | Filter by currency |
| created_after | datetime | Filter by creation date (inclusive) |
| created_before | datetime | Filter by creation date (exclusive) |
| limit | integer | Page size (default 20, max 100) |
| offset | integer | Offset for pagination (default 0) |

**Response 200:**
```json
{
  "data": [ /* array of PaymentResponse objects */ ],
  "pagination": {
    "total": 150,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

---

#### `POST /api/v1/payments/{payment_id}/confirm`

Server-side payment confirmation (for saved payment methods).

**Required role:** `service`, `admin`

**Request:**
```json
{
  "payment_method_id": "pm_card_visa"
}
```

**Response 200:** PaymentResponse with updated status.

---

#### `POST /api/v1/payments/{payment_id}/cancel`

Cancel a pending payment.

**Required role:** `service`, `admin`

**Request:** Empty body (or optional reason).
```json
{
  "reason": "Customer requested cancellation"
}
```

**Response 200:** PaymentResponse with `status: "canceled"`.

---

### 5.3 Refunds

#### `POST /api/v1/payments/{payment_id}/refund`

Initiate a full or partial refund.

**Required role:** `admin`

**Request:**
```json
{
  "amount": 2500,
  "reason": "Customer returned item"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| amount | integer | No | If omitted, full refund. Must be > 0 and <= remaining refundable amount. |
| reason | string | No | Max 255 chars |

**Response 201:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "re_1ABC123",
  "amount": 2500,
  "reason": "Customer returned item",
  "status": "pending",
  "created_at": "2026-06-16T16:00:00Z",
  "updated_at": "2026-06-16T16:00:00Z"
}
```

---

#### `GET /api/v1/payments/{payment_id}/refunds`

List refunds for a payment.

**Required role:** `admin`, `readonly`

**Response 200:**
```json
{
  "data": [ /* array of RefundResponse objects */ ],
  "pagination": {
    "total": 2,
    "limit": 20,
    "offset": 0,
    "has_more": false
  }
}
```

---

#### `GET /api/v1/refunds/{refund_id}`

Get refund details.

**Required role:** `admin`, `readonly`

**Response 200:** RefundResponse object.

---

### 5.4 Webhooks

#### `POST /api/v1/webhooks/stripe`

Stripe webhook endpoint.

**Authentication:** Stripe signature verification (not API key/JWT).

**Request:** Raw Stripe event payload (the route must read the raw body, not parsed JSON, for signature verification).

**Response 200:**
```json
{
  "received": true
}
```

**Response 400:** Invalid signature.

---

### 5.5 Reconciliation (Admin)

#### `POST /api/v1/admin/reconciliation/run`

Trigger a reconciliation run.

**Required role:** `admin`

**Request:**
```json
{
  "date_range_start": "2026-06-01T00:00:00Z",
  "date_range_end": "2026-06-16T00:00:00Z"
}
```

**Response 202:**
```json
{
  "report_id": "770e8400-e29b-41d4-a716-446655440002",
  "status": "in_progress",
  "message": "Reconciliation started."
}
```

---

#### `GET /api/v1/admin/reconciliation/reports`

List reconciliation reports.

**Required role:** `admin`

**Response 200:**
```json
{
  "data": [ /* array of ReportResponse objects */ ],
  "pagination": { "total": 5, "limit": 20, "offset": 0, "has_more": false }
}
```

---

#### `GET /api/v1/admin/reconciliation/reports/{report_id}`

Get a specific reconciliation report.

**Required role:** `admin`

**Response 200:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "date_range_start": "2026-06-01T00:00:00Z",
  "date_range_end": "2026-06-16T00:00:00Z",
  "total_internal": 150,
  "total_provider": 151,
  "matched_count": 149,
  "discrepancy_count": 2,
  "discrepancies": [
    {
      "type": "missing_internal",
      "provider_id": "pi_xyz",
      "details": "Payment exists in Stripe but not in internal database."
    },
    {
      "type": "amount_mismatch",
      "internal_id": "550e...",
      "provider_id": "pi_abc",
      "internal_amount": 5000,
      "provider_amount": 5500,
      "details": "Amount mismatch."
    }
  ],
  "status": "completed",
  "created_at": "2026-06-16T16:30:00Z",
  "completed_at": "2026-06-16T16:31:00Z"
}
```

## 6. Rate Limits

| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Payment creation | 30/min | Per API key |
| Payment status | 120/min | Per API key |
| Refunds | 10/min | Per API key |
| Webhooks | 300/min | Per source IP |
| Reconciliation | 5/min | Per API key |
| Health/Info | 60/min | Per source IP |
