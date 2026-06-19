# Security Model

## Threat Model Summary

PayGateway is a server-side component. The trust boundary is:
- **Trusted:** Your own backend services and admin users calling the API with valid API keys
- **Untrusted:** Public internet, frontend clients, webhook senders (even Stripe — signatures verified)

---

## Credential Security

### API Keys

- **Never stored in plaintext** — only a SHA-256 HMAC hash (`SHA256(salt + key)`) is persisted
- **Prefix-indexed** — first 8 characters stored for fast DB lookup without full key exposure
- **Salted hashing** — `API_KEY_SALT` prevents rainbow table attacks on the `key_hash` column
- **Shown once** — the plaintext key is returned only at creation time
- **Role-scoped** — each key carries a role (`admin`, `service`, `readonly`)
- **Expirable** — `expires_at` column supports automatic key rotation

### Stripe Keys

- `STRIPE_SECRET_KEY` lives only in server environment variables — never in frontend code, logs, or DB
- Clients receive only `client_secret` (payment-intent scoped, can't be used to create new charges)
- Frontend uses Stripe.js with the publishable key to tokenize card data — raw card numbers never reach PayGateway

### JWT

- Signed with `HS256` + `JWT_SECRET_KEY`
- Short-lived (default 15 minutes, configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`)
- No refresh tokens — re-authenticate to get a new token

---

## Transport Security

- All production traffic must be served over HTTPS (TLS 1.2+)
- Database connections use SSL (`DATABASE_SSL=true` enforces `sslmode=require`)
- CORS is restricted to `ALLOWED_ORIGINS` — set to only your actual frontend domains

---

## Idempotency & Replay Safety

All `POST` operations require an `Idempotency-Key` header:
- Keys are stored in the `idempotency_records` table with a TTL of 24 hours
- Duplicate requests with the same key return the cached response — no double charges
- Keys are scoped per API key, preventing cross-client replay

---

## Rate Limiting

Sliding-window rate limiting is enforced per API key (or IP if no key):

| Endpoint | Limit per 60 s |
|----------|---------------|
| `/api/v1/payments` | 30 |
| `/api/v1/refunds` | 10 |
| `/api/v1/admin/reconciliation` | 5 |
| `/api/v1/webhooks` | 300 |
| Default | 120 |

Exceeding limits returns `HTTP 429` with `Retry-After` header.

In-memory rate limiter is used by default (single instance). For multi-instance deployments, replace `InMemoryRateLimiter` with a Redis-backed implementation.

---

## Webhook Signature Verification

Stripe webhooks are verified before processing using HMAC-SHA256:

```
Stripe-Signature: t=<timestamp>,v1=<hmac>
```

- `STRIPE_WEBHOOK_SECRET` must match the secret from the Stripe dashboard webhook endpoint
- Signatures are verified by the official Stripe SDK (`stripe.Webhook.construct_event`)
- Invalid signatures return `HTTP 400 INVALID_SIGNATURE` — event is rejected entirely
- Timestamp tolerance: Stripe enforces a 5-minute tolerance by default

---

## Audit Logging

Every state-changing operation records an entry in `audit_log`:

| Field | Description |
|-------|-------------|
| `actor_id` | User or API key ID that performed the action |
| `actor_type` | `"user"` (API key auth) or derived from JWT |
| `action` | e.g. `payment.created`, `refund.created`, `payment.canceled` |
| `resource_type` | `payment`, `refund`, etc. |
| `resource_id` | UUID of affected record |
| `ip_address` | Client IP from request |
| `outcome` | `"success"` or `"failure"` |
| `timestamp` | UTC timestamp |

Audit records are write-only — no update or delete operations exist on `audit_log`.

---

## Input Validation

- All request bodies validated by Pydantic v2 before reaching business logic
- `amount`: must be positive integer, max 99 999 999 (Stripe limit)
- `currency`: exactly 3 characters
- `metadata`: max 20 keys, max 40-char keys, max 500-char values
- `payment_method_id`: non-empty string
- UUID path parameters: validated by FastAPI at the routing layer

---

## SQL Injection Prevention

- All DB queries use SQLAlchemy ORM with parameterized statements
- No raw SQL string interpolation anywhere in the codebase
- Alembic migrations use `op.alter_column()` / `op.add_column()` — no raw DDL string formatting

---

## Sensitive Data in Logs

The following are **never logged**:
- Full API keys (only the 8-char prefix appears in rate-limit keys)
- `client_secret` values
- Stripe secret keys
- JWT tokens

The `client_secret` is also stripped from `GET /payments` responses — it is only returned at creation time.

---

## Dependency Security

Pin all dependencies in `requirements.txt`. Run regularly:

```bash
pip audit           # check for known CVEs
pip list --outdated # find stale packages
```

Keep the Stripe SDK updated — new API versions add security fixes.

---

## Security Checklist Before Going Live

- [ ] `API_KEY_SALT` is a random 32-byte hex string (not `REPLACE_WITH_RANDOM_SALT`)
- [ ] `JWT_SECRET_KEY` is a random 64-byte hex string (not `REPLACE_WITH_RANDOM_SECRET`)
- [ ] `STRIPE_WEBHOOK_SECRET` is the real `whsec_...` from Stripe dashboard (not placeholder)
- [ ] `ALLOWED_ORIGINS` does not include `localhost` or wildcard `*`
- [ ] `DATABASE_SSL=true`
- [ ] HTTPS enforced (TLS termination at load balancer or reverse proxy)
- [ ] `ENVIRONMENT=production` (disables verbose SQLAlchemy echo logging)
- [ ] Audit log retention policy defined (recommend 90 days minimum)
- [ ] Rate limiting backed by Redis for multi-instance deployments
- [ ] API keys rotated from the test keys used during development
