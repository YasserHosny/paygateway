# Payment Gateway Core Service — Security Design

## 1. Threat Model

### Assets
- Payment data (amounts, statuses, customer references)
- Stripe API credentials (secret key, webhook secret)
- API keys (hashed in database)
- Audit logs (integrity-critical)
- Customer metadata

### Threat Actors
- External attackers (internet-facing API)
- Compromised client applications
- Malicious insiders with API access
- Automated bots (credential stuffing, payment fraud)

### Attack Vectors
1. **Unauthorized API access:** Missing or weak authentication.
2. **Stripe credential theft:** Secrets exposed in code, logs, or environment.
3. **Webhook spoofing:** Fake webhook events to manipulate payment status.
4. **Idempotency abuse:** Replay attacks to double-process payments.
5. **SQL injection / input validation bypass:** Malformed input.
6. **Rate limiting bypass:** DDoS or brute-force attacks.
7. **Audit log tampering:** Modifying or deleting audit trail.
8. **Man-in-the-middle:** Intercepting API traffic.

## 2. Authentication

### 2.1 API Key Authentication

- API keys are generated as `pgw_{env}_{random_32_chars}` (e.g., `pgw_live_aBcD...`).
- Only the SHA-256 hash of the key is stored in the database.
- The first 8 characters (`key_prefix`) are stored in plaintext for identification/lookup.
- Lookup: find by prefix, then verify full hash.
- Keys can be deactivated without deletion (soft disable).
- Keys can have optional expiry dates.

### 2.2 JWT Authentication

- Used for user-facing clients (Angular, Flutter).
- JWT signed with RS256 or HS256 (configurable).
- Token payload includes: `sub` (user ID), `role`, `iat`, `exp`.
- Short-lived access tokens (15 minutes recommended).
- Refresh tokens managed by the client application's auth system (not by this service).
- The service validates JWTs but does not issue them — the consuming application's auth system issues tokens.

### 2.3 Webhook Authentication

- Stripe webhooks authenticated via `Stripe-Signature` header.
- Verified using `stripe.Webhook.construct_event()` with `STRIPE_WEBHOOK_SECRET`.
- Replay protection: Stripe includes a timestamp in the signature; reject events older than 5 minutes (configurable tolerance).

## 3. Authorization

### 3.1 Role-Based Access Control (RBAC)

| Role | Permissions |
|------|-------------|
| admin | All operations: create payments, refunds, reconciliation, view audit logs, manage API keys |
| service | Create payments, confirm payments, cancel payments, view payment status |
| readonly | View payment status, view refund status |

### 3.2 Enforcement

- Roles are checked in middleware/dependency injection before the route handler executes.
- Role is extracted from the API key record or JWT claims.
- Missing or insufficient role returns 403 Forbidden.

## 4. Input Validation

### 4.1 Pydantic Validation

- All request bodies validated by Pydantic models before reaching service layer.
- Strict type checking enabled.
- String fields have max length constraints.
- Numeric fields have min/max constraints.
- Enum fields restricted to valid values.

### 4.2 Specific Validations

| Field | Validation |
|-------|-----------|
| amount | Positive integer, max 99,999,999 |
| currency | 3-character string, valid ISO 4217 |
| idempotency_key | 1-255 characters, alphanumeric + hyphens + underscores |
| metadata keys | Max 20 keys, key max 40 chars |
| metadata values | String, max 500 chars per value |
| customer_id | Max 255 chars |
| description | Max 500 chars |
| payment_id / refund_id | Valid UUID v4 format |

### 4.3 SQL Injection Prevention

- SQLAlchemy ORM with parameterized queries (no raw SQL string interpolation).
- JSONB fields stored/retrieved via ORM, never interpolated.

## 5. Transport Security

- HTTPS enforced in production (via reverse proxy / load balancer).
- HSTS header: `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- No sensitive data in URL query parameters (payment IDs in path are UUIDs, not sensitive).

## 6. CORS Configuration

```python
CORSMiddleware(
    allow_origins=settings.ALLOWED_ORIGINS,  # Explicit list, never ["*"] in production
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=600,
)
```

## 7. Secrets Management

### 7.1 Environment Variables

| Variable | Description |
|----------|-------------|
| STRIPE_SECRET_KEY | Stripe API secret key |
| STRIPE_PUBLISHABLE_KEY | Stripe publishable key (for client reference) |
| STRIPE_WEBHOOK_SECRET | Webhook signature verification secret |
| STRIPE_API_VERSION | Pinned Stripe API version |
| DATABASE_URL | PostgreSQL connection string |
| REDIS_URL | Redis connection string |
| JWT_SECRET_KEY | JWT signing key (if using HS256) |
| JWT_ALGORITHM | JWT algorithm (RS256 or HS256) |
| ALLOWED_ORIGINS | Comma-separated CORS origins |
| API_KEY_SALT | Additional salt for API key hashing |

### 7.2 Rules

- Never commit secrets to git.
- `.env` in `.gitignore`.
- `.env.example` contains variable names with placeholder values.
- In production, use the platform's secrets management (AWS Secrets Manager, GCP Secret Manager, Vault, etc.).
- Secrets never appear in logs, error messages, or API responses.

## 8. Rate Limiting

### 8.1 Implementation

- Token bucket or sliding window algorithm.
- State stored in Redis (or in-memory for single-instance development).
- Keyed by API key (for authenticated endpoints) or IP address (for unauthenticated endpoints).

### 8.2 Response

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1718551200

{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded. Retry after 30 seconds.",
    "details": {}
  }
}
```

## 9. Logging and Monitoring Security

### 9.1 What to Log
- Request method, path, status code, latency.
- Authentication outcome (success/failure, which key/user).
- Payment operations (create, confirm, refund) with payment ID.
- Webhook events received and processing outcome.
- Rate limit events.
- Errors and exceptions (with stack trace in non-production).

### 9.2 What NOT to Log
- Stripe secret keys.
- API key values (only prefix).
- JWT tokens.
- `client_secret` values.
- Full request/response bodies containing sensitive data.
- Raw card numbers (never handled, but defense in depth).

### 9.3 Log Format

Structured JSON logging:
```json
{
  "timestamp": "2026-06-16T15:30:00Z",
  "level": "INFO",
  "request_id": "req_abc123",
  "message": "Payment created",
  "payment_id": "550e8400-...",
  "amount": 5000,
  "currency": "USD"
}
```

## 10. PCI DSS Considerations

- The service never receives, processes, stores, or transmits cardholder data (card numbers, CVVs, expiration dates).
- Card data is collected by Stripe.js or Flutter Stripe SDK directly and sent to Stripe.
- The service only handles Stripe tokens, PaymentIntent IDs, and client secrets.
- This keeps the service in **SAQ-A** or **SAQ-A-EP** scope, depending on the integration method.
- Regular vulnerability scans and dependency updates are recommended.

## 11. Dependency Security

- Pin all dependencies to specific versions.
- Regular dependency audits (`pip-audit`, `safety`).
- Minimal dependency footprint — only use what is necessary.
- No unnecessary dev dependencies in production images.

## 12. API Key Lifecycle

1. **Generation:** Admin generates a new API key via CLI or admin endpoint.
2. **Distribution:** Full key shown once. After creation, only the prefix is retrievable.
3. **Usage:** Client includes key in `X-API-Key` header.
4. **Rotation:** New key generated, old key deactivated after grace period.
5. **Revocation:** Key set to `is_active = false`. Immediate effect.
6. **Expiry:** Optional. Expired keys rejected automatically.
