# Deployment Guide

## Prerequisites

- Python 3.12+ or Docker
- PostgreSQL 14+ (Supabase recommended)
- Stripe account (test or live keys)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL DSN | `postgresql+asyncpg://user:pass@host:5432/db` |
| `DATABASE_URL_SYNC` | Sync DSN (Alembic migrations) | `postgresql://user:pass@host:5432/db` |
| `DATABASE_SSL` | Enforce SSL | `true` |
| `STRIPE_SECRET_KEY` | Stripe secret key | `sk_live_...` or `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key | `pk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook endpoint secret | `whsec_...` |
| `STRIPE_API_VERSION` | Stripe API version | `2026-05-27.dahlia` |
| `JWT_SECRET_KEY` | Random secret for JWT signing | `<64-char random string>` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `API_KEY_SALT` | Salt for API key hashing | `<32-char random string>` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `https://app.example.com` |
| `ENVIRONMENT` | Runtime environment | `production` |
| `LOG_LEVEL` | Log verbosity | `INFO` |

### Generating Secrets

```bash
# JWT secret (64 bytes hex)
python3 -c "import secrets; print(secrets.token_hex(64))"

# API key salt (32 bytes hex)
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Supabase Connection

Use the **session pooler** URL (has IPv4, works everywhere):
```
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL_SYNC=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Find your pooler URL at: Supabase dashboard → Project Settings → Database → Connection pooling → Session mode.

---

## Local Development

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run migrations

```bash
alembic upgrade head
```

### 3. Start the server

```bash
uvicorn paygateway.main:app --host 127.0.0.1 --port 8765 --env-file .env --reload
```

API docs available at `http://127.0.0.1:8765/docs`.

---

## Docker

### Build and run

```bash
docker compose up --build
```

The `docker-compose.yml` starts:
- `api` — PayGateway FastAPI server on port `8765`
- `db` — PostgreSQL 16 (for local dev without Supabase)

### Production build

```bash
docker build -t paygateway:latest .
docker run -d \
  --env-file .env \
  -p 8765:8765 \
  paygateway:latest
```

### Environment variables in Docker

Pass via `--env-file` or `-e` flags. Never bake secrets into the image.

---

## Database Migrations

Migrations use Alembic. Always run before starting the server in a new environment.

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# Rollback one step
alembic downgrade -1

# Generate a new migration (auto-detect model changes)
alembic revision --autogenerate -m "add_column_x"
```

### Migration chain

| Revision | Description |
|----------|-------------|
| `0001` | Initial schema — payments, refunds, api_keys, audit_log, idempotency, webhooks, reconciliation |
| `0002` | Add `updated_at` to `api_keys` |
| `0003` | Rename `payments.metadata_` column to `metadata` |

---

## Production Checklist

- [ ] `ENVIRONMENT=production` in `.env`
- [ ] `STRIPE_SECRET_KEY` is a live key (`sk_live_...`)
- [ ] `STRIPE_WEBHOOK_SECRET` is set from Stripe dashboard webhook endpoint
- [ ] `JWT_SECRET_KEY` is a cryptographically random 64-byte string
- [ ] `API_KEY_SALT` is a cryptographically random 32-byte string
- [ ] `ALLOWED_ORIGINS` contains only your actual frontend domains
- [ ] `DATABASE_SSL=true`
- [ ] TLS termination in front of the API (nginx, AWS ALB, Cloudflare)
- [ ] Health check configured at `/health` in your load balancer
- [ ] `.env` not committed to version control (confirmed in `.gitignore`)
- [ ] API keys with minimal roles issued for each integration

---

## Stripe Webhook Setup

1. Go to Stripe Dashboard → Developers → Webhooks → Add endpoint
2. Set URL: `https://your-domain.com/api/v1/webhooks/stripe`
3. Select events: `payment_intent.*`, `charge.*`, `charge.refund.updated`
4. Copy the **Signing secret** (`whsec_...`) → set as `STRIPE_WEBHOOK_SECRET`

For local testing, use [Stripe CLI](https://stripe.com/docs/stripe-cli):
```bash
stripe login
stripe listen --forward-to http://127.0.0.1:8765/api/v1/webhooks/stripe
```
The CLI prints a temporary `whsec_...` — use it as `STRIPE_WEBHOOK_SECRET` during local dev.

---

## Health Monitoring

The `/health` endpoint returns database connectivity status:

```bash
curl https://your-domain.com/health
# {"status":"healthy","checks":{"database":"ok"},"timestamp":"..."}
```

Configure your load balancer to poll `/health` every 30 seconds. If `status` is `"degraded"`, remove the instance from rotation.

---

## Background Jobs

In `staging` and `production` environments, the scheduler starts automatically on server boot:

- **Nightly reconciliation** — compares DB state vs Stripe, flags mismatches
- **Idempotency cleanup** — removes expired idempotency records (>24h)

In `development`, jobs are disabled to avoid noise. You can trigger reconciliation manually via `POST /api/v1/admin/reconciliation/run`.
