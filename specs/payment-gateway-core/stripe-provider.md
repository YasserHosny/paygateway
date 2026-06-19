# Payment Gateway Core Service — Stripe Provider Design

## 1. Overview

The Stripe provider adapter implements the `PaymentProvider` interface using Stripe's Python SDK (`stripe` package). It translates between the normalized provider interface and Stripe's API.

## 2. Dependencies

```
stripe>=8.0.0
httpx>=0.27.0  # For async HTTP if needed beyond stripe SDK
```

## 3. Configuration

### Environment Variables

| Variable | Example | Description |
|----------|---------|-------------|
| STRIPE_SECRET_KEY | sk_test_51... | Stripe secret API key |
| STRIPE_PUBLISHABLE_KEY | pk_test_51... | Stripe publishable key (returned to clients for reference) |
| STRIPE_WEBHOOK_SECRET | whsec_... | Webhook signing secret |
| STRIPE_API_VERSION | 2024-12-18 | Pinned API version |

### Initialization

```python
class StripeProvider(PaymentProvider):
    def __init__(self, config: Settings):
        self._client = stripe.StripeClient(
            api_key=config.STRIPE_SECRET_KEY,
            stripe_version=config.STRIPE_API_VERSION,
        )
        self._webhook_secret = config.STRIPE_WEBHOOK_SECRET
```

## 4. Method Implementations

### 4.1 create_payment_intent

```
Stripe API: POST /v1/payment_intents
SDK: self._client.payment_intents.create(...)
```

**Mapping:**
- `amount` → `amount`
- `currency` → `currency`
- `idempotency_key` → passed via `stripe_version` options
- `customer_id` → If provider customer exists, pass `customer`; otherwise omit
- `description` → `description`
- `metadata` → `metadata`
- `automatic_payment_methods.enabled` → `True` (let Stripe handle payment method selection)

**Response mapping:**
- `pi.id` → `provider_id`
- `pi.status` → map via status table
- `pi.client_secret` → `client_secret`
- `pi.amount` → `amount`
- `pi.currency` → `currency` (uppercase)

### 4.2 confirm_payment_intent

```
Stripe API: POST /v1/payment_intents/{id}/confirm
SDK: self._client.payment_intents.confirm(...)
```

- Pass `payment_method` parameter.
- Forward idempotency key.

### 4.3 cancel_payment_intent

```
Stripe API: POST /v1/payment_intents/{id}/cancel
SDK: self._client.payment_intents.cancel(...)
```

- Pass `cancellation_reason` if provided (mapped to Stripe's allowed values: `duplicate`, `fraudulent`, `requested_by_customer`, `abandoned`).

### 4.4 get_payment_intent

```
Stripe API: GET /v1/payment_intents/{id}
SDK: self._client.payment_intents.retrieve(...)
```

### 4.5 create_refund

```
Stripe API: POST /v1/refunds
SDK: self._client.refunds.create(...)
```

- `payment_intent` → provider payment ID
- `amount` → refund amount (omit for full refund)
- `reason` → mapped to Stripe values: `duplicate`, `fraudulent`, `requested_by_customer`
- Forward idempotency key.

### 4.6 get_refund

```
Stripe API: GET /v1/refunds/{id}
SDK: self._client.refunds.retrieve(...)
```

### 4.7 verify_webhook

```python
async def verify_webhook(self, payload: bytes, headers: dict) -> ProviderWebhookEvent:
    sig_header = headers.get("stripe-signature")
    if not sig_header:
        raise ProviderWebhookVerificationError(
            message="Missing Stripe-Signature header",
            provider="stripe",
        )
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=self._webhook_secret,
        )
    except stripe.SignatureVerificationError as e:
        raise ProviderWebhookVerificationError(
            message=str(e),
            provider="stripe",
        )

    payment_id = None
    refund_id = None
    data_object = event.data.object

    if hasattr(data_object, "id"):
        if event.type.startswith("payment_intent"):
            payment_id = data_object.id
        elif event.type.startswith("charge.refund"):
            refund_id = data_object.id
            payment_id = getattr(data_object, "payment_intent", None)

    return ProviderWebhookEvent(
        event_id=event.id,
        event_type=event.type,
        payload=event.to_dict(),
        payment_provider_id=payment_id,
        refund_provider_id=refund_id,
    )
```

### 4.8 list_payment_intents

```python
async def list_payment_intents(
    self,
    created_after: datetime,
    created_before: datetime,
    limit: int = 100,
    starting_after: Optional[str] = None,
) -> tuple[list[ProviderPaymentIntent], Optional[str]]:
    params = {
        "created": {
            "gte": int(created_after.timestamp()),
            "lt": int(created_before.timestamp()),
        },
        "limit": limit,
    }
    if starting_after:
        params["starting_after"] = starting_after

    result = self._client.payment_intents.list(**params)
    intents = [self._map_payment_intent(pi) for pi in result.data]
    next_cursor = result.data[-1].id if result.has_more else None
    return intents, next_cursor
```

## 5. Status Mapping

### Payment Intent Status Mapping

| Stripe Status | Normalized Status |
|---------------|------------------|
| requires_payment_method | pending |
| requires_confirmation | pending |
| requires_action | requires_action |
| processing | processing |
| succeeded | succeeded |
| canceled | canceled |
| requires_capture | processing |

### Refund Status Mapping

| Stripe Status | Normalized Status |
|---------------|------------------|
| pending | pending |
| succeeded | succeeded |
| failed | failed |
| canceled | failed |

## 6. Error Mapping

| Stripe Exception | Provider Error |
|------------------|---------------|
| stripe.AuthenticationError | ProviderAuthenticationError |
| stripe.PermissionError | ProviderAuthenticationError |
| stripe.InvalidRequestError | ProviderValidationError |
| stripe.APIConnectionError | ProviderConnectionError |
| stripe.RateLimitError | ProviderRateLimitError |
| stripe.APIError | ProviderError |
| stripe.SignatureVerificationError | ProviderWebhookVerificationError |

## 7. Stripe Test Mode

### Test Card Numbers

| Card Number | Behavior |
|------------|----------|
| 4242424242424242 | Succeeds |
| 4000000000003220 | Requires 3D Secure |
| 4000000000000002 | Declined (generic) |
| 4000000000009995 | Insufficient funds |
| 4000000000000069 | Expired card |

### Test Webhook Events

Use Stripe CLI for local webhook testing:
```bash
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
stripe trigger payment_intent.succeeded
```

### Environment Setup

```env
STRIPE_SECRET_KEY=sk_test_51...
STRIPE_PUBLISHABLE_KEY=pk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_...  # From `stripe listen` output
STRIPE_API_VERSION=2024-12-18
```

## 8. Async Considerations

The `stripe` Python SDK supports sync operations. For async usage:

**Option A (recommended for v1):** Use `stripe` SDK synchronously within `asyncio.to_thread()`:
```python
async def create_payment_intent(self, ...):
    result = await asyncio.to_thread(
        self._client.payment_intents.create,
        amount=amount,
        currency=currency,
        ...
    )
    return self._map_payment_intent(result)
```

**Option B (future):** Use `httpx` AsyncClient to call Stripe REST API directly. More complex but fully async.

Option A is recommended for the initial implementation because it's simpler and the `stripe` SDK handles retry logic, idempotency, and error handling.

## 9. Idempotency Key Handling

Stripe natively supports idempotency keys. Pass them via the SDK:

```python
self._client.payment_intents.create(
    amount=amount,
    currency=currency,
    ...,
    options={"idempotency_key": f"stripe_{idempotency_key}"},
)
```

Prefix with `stripe_` to namespace the key in case different providers have different key requirements.
