# Authentication & Authorization

## Overview

PayGateway supports two authentication methods:

| Method | Best For |
|--------|---------|
| API Key (`X-API-Key`) | Server-to-server, backend services, CI/CD |
| JWT Bearer (`Authorization: Bearer`) | Short-lived sessions, dashboard access |

All `/api/v1/*` endpoints require authentication. Health endpoints (`/health`, `/info`) are public.

---

## API Key Authentication

### How It Works

1. An API key is generated (e.g. `pgw_test_aBcDeFgHiJkLmNoPqRsTuVwXyZ12`)
2. The first 8 characters (`pgw_test`) are stored as `key_prefix` for fast lookup
3. The full key is hashed with SHA-256 + salt and stored as `key_hash`
4. **The plaintext key is never stored** — only shown once at creation

**Request header:**
```
X-API-Key: pgw_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ12
```

**Validation flow:**
1. Extract first 8 chars → query `api_keys WHERE key_prefix = $1 AND is_active = true`
2. Hash incoming key with `SHA-256(API_KEY_SALT + key)` → compare to `key_hash`
3. Check `expires_at` if set
4. Update `last_used_at` on success

### Creating an API Key

Insert directly into the database (admin operation):

```sql
INSERT INTO api_keys (id, name, key_hash, key_prefix, role, is_active, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'My Service Key',
  sha256(concat('YOUR_SALT', 'pgw_live_YOURKEYHERE')),
  'pgw_live',   -- first 8 chars of the key
  'admin',       -- or 'service' or 'readonly'
  true,
  now(),
  now()
);
```

Or use the seed script pattern from `tests/conftest.py` for programmatic creation.

### API Key Roles

| Role | Permissions |
|------|------------|
| `admin` | Full access — all endpoints including refunds and reconciliation |
| `service` | Create, confirm, cancel payments (no refunds, no reconciliation) |
| `readonly` | GET endpoints only — no mutations |

### Key Expiry

Set `expires_at` to automatically invalidate keys after a date:
```sql
UPDATE api_keys SET expires_at = '2027-01-01 00:00:00+00' WHERE id = '...';
```

The API returns `HTTP 401` with `"API key expired"` after that timestamp.

---

## JWT Authentication

### How It Works

JWTs are verified using `HS256` with `JWT_SECRET_KEY` from your environment.

**Request header:**
```
Authorization: Bearer eyJhbGci...
```

**Required JWT claims:**

| Claim | Type | Description |
|-------|------|-------------|
| `sub` | string | User identifier (required) |
| `role` | string | One of `admin`, `service`, `readonly` (defaults to `readonly` if absent) |
| `exp` | Unix timestamp | Expiry (standard JWT) |

**Example payload:**
```json
{
  "sub": "user-123",
  "role": "admin",
  "exp": 1750349869
}
```

### Generating a JWT (example)

```python
import time
from jose import jwt

token = jwt.encode(
    {
        "sub": "user-123",
        "role": "admin",
        "exp": int(time.time()) + 900,  # 15 minutes
    },
    key="your-jwt-secret",
    algorithm="HS256",
)
```

Access token lifetime is controlled by `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default: 15 minutes).

---

## Role-Based Access Control

Endpoints enforce roles via the `require_role(*roles)` dependency:

| Endpoint | admin | service | readonly |
|----------|-------|---------|----------|
| `POST /payments` | ✓ | ✓ | ✗ |
| `GET /payments/{id}` | ✓ | ✓ | ✓ |
| `GET /payments` | ✓ | ✗ | ✓ |
| `POST /payments/{id}/confirm` | ✓ | ✓ | ✗ |
| `POST /payments/{id}/cancel` | ✓ | ✓ | ✗ |
| `POST /payments/{id}/refund` | ✓ | ✗ | ✗ |
| `GET /payments/{id}/refunds` | ✓ | ✗ | ✓ |
| `GET /refunds/{id}` | ✓ | ✗ | ✓ |
| `POST /admin/reconciliation/run` | ✓ | ✗ | ✗ |
| `GET /admin/reconciliation/reports` | ✓ | ✗ | ✗ |

Unauthorized access returns:
```json
HTTP 403
{
  "detail": {
    "error": {
      "code": "FORBIDDEN",
      "message": "Insufficient permissions",
      "details": {}
    }
  }
}
```

---

## Error Responses

| HTTP | Code | Cause |
|------|------|-------|
| 401 | `UNAUTHORIZED` | Missing header, invalid key/token |
| 401 | `UNAUTHORIZED` | API key expired |
| 403 | `FORBIDDEN` | Valid key but insufficient role |
| 503 | `SERVICE_UNAVAILABLE` | Database unreachable during auth lookup |

---

## Security Best Practices

- **Never commit API keys or JWT secrets** to version control
- Rotate `API_KEY_SALT` and `JWT_SECRET_KEY` if either is compromised (requires re-hashing all keys)
- Use `readonly` role for analytics dashboards — never `admin`
- Set `expires_at` on API keys for external integrations
- Use short-lived JWTs (15 min) for user sessions
- Store API keys in secrets managers (AWS Secrets Manager, Vault) in production
