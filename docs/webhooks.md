# Webhooks

## What Are Stripe Webhooks?

When something happens in Stripe (a payment succeeds, a refund completes), Stripe sends an HTTP `POST` to your configured endpoint. PayGateway receives these events and uses them to keep its local database in sync with Stripe's source of truth.

---

## Setup

### 1. Stripe Dashboard

1. Go to **Developers → Webhooks → Add endpoint**
2. URL: `https://your-domain.com/api/v1/webhooks/stripe`
3. Select events (minimum recommended):
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
   - `payment_intent.canceled`
   - `charge.refund.updated`
4. Click **Add endpoint**
5. Copy the **Signing secret** (`whsec_...`) → set as `STRIPE_WEBHOOK_SECRET` in your environment

### 2. Local Development

Use [Stripe CLI](https://stripe.com/docs/stripe-cli) to forward events to your local server:

```bash
# Install Stripe CLI, then:
stripe login
stripe listen --forward-to http://127.0.0.1:8765/api/v1/webhooks/stripe
```

The CLI outputs a temporary `whsec_...` — set it as `STRIPE_WEBHOOK_SECRET` in your local `.env`.

Trigger a test event:
```bash
stripe trigger payment_intent.succeeded
```

---

## Endpoint Details

```
POST /api/v1/webhooks/stripe
```

- **No API key required** — Stripe signs events with `STRIPE_WEBHOOK_SECRET`
- **Content-Type:** `application/json` (raw body preserved for signature verification)
- **Required header:** `Stripe-Signature: t=<timestamp>,v1=<hmac>`
- **Rate limit:** 300 requests per 60 seconds

---

## Signature Verification

Every inbound webhook is verified before processing:

1. Stripe includes `Stripe-Signature` header with `t` (timestamp) and `v1` (HMAC)
2. PayGateway calls `stripe.Webhook.construct_event(payload, sig_header, webhook_secret)`
3. If signature is invalid → `HTTP 400 INVALID_SIGNATURE`, event discarded
4. If valid → event processed

Stripe's default tolerance is **300 seconds** (5 minutes). Events older than this are rejected automatically.

---

## Events Processed

| Stripe Event | PayGateway Action |
|-------------|-------------------|
| `payment_intent.succeeded` | Update payment `status → succeeded`, set `confirmed_at` |
| `payment_intent.payment_failed` | Update payment `status → failed`, store `failure_code` and `failure_message` |
| `payment_intent.canceled` | Update payment `status → canceled`, set `canceled_at` |
| `charge.refund.updated` | Sync refund `status` and `failure_reason` |

All processed events are stored in `webhook_events` table for audit purposes.

---

## Event Idempotency

Stripe may deliver the same event more than once. PayGateway handles this safely:
- Each event is stored with its Stripe `event_id`
- Duplicate event IDs are detected and skipped
- No double state mutations or double refunds

---

## Response Format

On success:
```json
HTTP 200
{ "received": true }
```

On signature failure:
```json
HTTP 400
{
  "detail": {
    "error": {
      "code": "INVALID_SIGNATURE",
      "message": "No signatures found matching the expected signature for payload",
      "details": {}
    }
  }
}
```

Always return `200` quickly — Stripe retries events that receive non-2xx responses.

---

## Retry Behavior (Stripe Side)

If PayGateway returns an error or times out, Stripe retries the event:

| Attempt | Delay |
|---------|-------|
| 1st retry | ~1 hour |
| 2nd retry | ~4 hours |
| Subsequent | Increasing intervals up to 72 hours |

Total retry window: **72 hours**. After that, the event is marked as failed in the Stripe dashboard.

---

## Debugging Webhooks

### View events in Stripe Dashboard

Developers → Webhooks → select your endpoint → **Recent deliveries**

You can see the request body, response, and retry history for each event.

### Check webhook_events table

```sql
SELECT event_id, event_type, processed_at, created_at
FROM webhook_events
ORDER BY created_at DESC
LIMIT 20;
```

### Re-deliver a failed event

In Stripe dashboard, click any failed delivery → **Resend**. PayGateway's idempotency handling will safely skip already-processed events.

---

## Adding New Event Types

To handle additional Stripe events, extend `webhook_service.py`:

```python
# src/paygateway/services/webhook_service.py

async def _handle_event(db, event_type: str, data_object: dict) -> None:
    if event_type == "payment_intent.succeeded":
        await _handle_payment_intent_succeeded(db, data_object)
    elif event_type == "my_new_event.type":
        await _handle_my_new_event(db, data_object)
    # unhandled events are silently ignored (no error)
```

Also add the event to your Stripe webhook endpoint's subscribed events in the dashboard.
