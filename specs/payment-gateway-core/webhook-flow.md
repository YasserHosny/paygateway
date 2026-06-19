# Payment Gateway Core Service — Webhook Flow

## 1. Overview

Webhooks are the primary mechanism for receiving asynchronous payment status updates from Stripe. The service must receive, verify, deduplicate, and process webhook events reliably.

## 2. Flow Diagram

```
Stripe Event Occurs
        |
        v
POST /api/v1/webhooks/stripe
        |
        v
+--[1. Read Raw Body]--+
        |
        v
+--[2. Verify Signature]--+
        |                   |
     Valid              Invalid
        |                   |
        v                   v
+--[3. Parse Event]--+  Return 400
        |
        v
+--[4. Deduplication Check]--+
        |                      |
   New Event             Already Processed
        |                      |
        v                      v
+--[5. Store Event]--+    Return 200
        |
        v
+--[6. Dispatch to Handler]--+
        |                      |
     Success               Failure
        |                      |
        v                      v
+--[7. Mark Processed]--+  Leave unprocessed
        |                (Stripe retries)
        v
   Return 200
```

## 3. Step Details

### Step 1: Read Raw Body

The webhook endpoint must read the **raw request body** (bytes), not the parsed JSON. Stripe's signature verification requires the exact raw payload.

```python
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
```

### Step 2: Verify Signature

Use the Stripe provider's `verify_webhook` method which calls `stripe.Webhook.construct_event()`.

- If the signature is missing or invalid, return `400 Bad Request`.
- Stripe includes a timestamp in the signature. Events older than the tolerance window (default: 5 minutes, configurable) are rejected to prevent replay attacks.

### Step 3: Parse Event

After verification, the event is returned as a `ProviderWebhookEvent` dataclass with:
- `event_id`: Unique event identifier from Stripe.
- `event_type`: Event type string (e.g., `payment_intent.succeeded`).
- `payload`: Full event data.
- `payment_provider_id`: Associated payment intent ID (if applicable).
- `refund_provider_id`: Associated refund ID (if applicable).

### Step 4: Deduplication Check

Query `webhook_events` table for `event_id`:
- If found with `processed = true`, return `200 OK` immediately (already handled).
- If found with `processed = false`, attempt reprocessing (previous attempt may have failed).
- If not found, proceed to store and process.

### Step 5: Store Event

Insert the event into `webhook_events` table with `processed = false`. Use `INSERT ... ON CONFLICT DO NOTHING` to handle race conditions from concurrent webhook deliveries.

### Step 6: Dispatch to Handler

Route the event to the appropriate handler based on `event_type`:

| Event Type | Handler Action |
|-----------|----------------|
| `payment_intent.succeeded` | Update payment status to `succeeded`, set `confirmed_at` |
| `payment_intent.payment_failed` | Update payment status to `failed`, record failure code/message |
| `payment_intent.canceled` | Update payment status to `canceled`, set `canceled_at` |
| `payment_intent.processing` | Update payment status to `processing` |
| `payment_intent.requires_action` | Update payment status to `requires_action` |
| `charge.refunded` | Update refund status to `succeeded`, update payment status to `refunded` or `partially_refunded` |
| `charge.refund.updated` | Update refund status based on event |
| `charge.dispute.created` | Update payment status to `disputed`, log details |
| `charge.dispute.closed` | Update dispute resolution in metadata, log details |

Unhandled event types are logged and acknowledged (return 200).

### Step 7: Mark Processed

After successful handling, update the `webhook_events` record:
- Set `processed = true`.
- Set `processed_at = now()`.

If handling fails, leave `processed = false` and store the error in `processing_error`. Return a non-200 status so Stripe retries.

## 4. Handler Details

### payment_intent.succeeded

```
1. Find internal payment by external_id matching the PaymentIntent ID.
2. If not found, log warning and return (orphan event).
3. Update payment:
   - status = "succeeded"
   - confirmed_at = event timestamp
   - updated_at = now()
4. Create audit log entry:
   - action = "payment.confirmed_via_webhook"
   - actor_type = "webhook"
   - outcome = "success"
```

### payment_intent.payment_failed

```
1. Find internal payment by external_id.
2. Update payment:
   - status = "failed"
   - failure_code = event.data.object.last_payment_error.code
   - failure_message = event.data.object.last_payment_error.message
   - updated_at = now()
3. Create audit log entry:
   - action = "payment.failed_via_webhook"
   - outcome = "failure"
   - details includes failure code and message
```

### charge.refunded

```
1. Extract payment_intent ID from the charge.
2. Find internal payment by external_id.
3. Find internal refund by matching provider refund ID.
4. Update refund status = "succeeded".
5. Calculate total refunded amount for the payment.
6. If total refunded == original amount:
   - payment status = "refunded"
   Else:
   - payment status = "partially_refunded"
7. Create audit log entry.
```

### charge.dispute.created

```
1. Find internal payment by external_id (from charge.payment_intent).
2. Update payment status = "disputed".
3. Store dispute details in payment metadata.
4. Create audit log entry with dispute details.
```

## 5. Error Handling and Retries

### Service-Side Errors

- If the handler throws an exception, catch it, log it, store it in `processing_error`, and return `500` so Stripe retries.
- If the payment/refund referenced by the event doesn't exist internally (yet), return `200` but log a warning. The event will be stored and can be reconciled later.

### Stripe Retry Behavior

- Stripe retries failed webhook deliveries (non-2xx responses) with exponential backoff.
- Retries continue for up to 3 days.
- The service must be idempotent — processing the same event twice has no additional effect.

### Ordering

- Stripe does not guarantee event ordering.
- Handlers must be defensive: check current state before applying transitions.
- Example: if a `payment_intent.succeeded` event arrives but the payment is already `refunded`, do not overwrite the status.

## 6. State Machine

Payment status transitions allowed via webhooks:

```
pending ──────────> processing
pending ──────────> requires_action
pending ──────────> succeeded
pending ──────────> failed
pending ──────────> canceled
processing ───────> succeeded
processing ───────> failed
requires_action ──> succeeded
requires_action ──> failed
requires_action ──> canceled
succeeded ────────> refunded
succeeded ────────> partially_refunded
succeeded ────────> disputed
partially_refunded > refunded
partially_refunded > disputed
```

Invalid transitions are logged but not applied. The payment retains its current state.

## 7. Monitoring

- Alert on: high rate of signature verification failures (potential attack).
- Alert on: events stuck in `processed = false` for > 1 hour.
- Alert on: dispute events (immediate attention needed).
- Metric: webhook processing latency.
- Metric: events received per minute by type.
- Metric: processing success/failure rate.

## 8. Testing Webhooks

### Local Development

Use Stripe CLI:
```bash
# Start listening and forwarding
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe

# Trigger specific events
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
stripe trigger charge.refunded
```

### Integration Tests

Construct events programmatically:
```python
def build_test_event(event_type: str, payment_intent_id: str) -> bytes:
    """Build a raw webhook payload for testing."""
    event = {
        "id": f"evt_test_{uuid4().hex[:8]}",
        "type": event_type,
        "data": {
            "object": {
                "id": payment_intent_id,
                "object": "payment_intent",
                "status": "succeeded",
                "amount": 5000,
                "currency": "usd",
            }
        },
    }
    return json.dumps(event).encode()
```

Sign test events using the test webhook secret for integration tests, or mock the verification step for unit tests.
