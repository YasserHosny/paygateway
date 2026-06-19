# Client Integration Guide

How to integrate PayGateway into your frontend (Angular, Flutter, or any web/mobile app).

---

## The Golden Rule

> **Your Stripe secret key (`sk_*`) must never leave your server.**  
> Clients only receive the `client_secret` from a specific payment intent, which is scoped and harmless.

PayGateway enforces this by design — clients call PayGateway (your server), not Stripe directly.

---

## Integration Architecture

```
┌─────────────────┐     1. Create payment      ┌──────────────────┐
│  Frontend App   │ ─────────────────────────> │  PayGateway API  │
│  (Angular/      │ <─ { client_secret } ────── │  (your server)   │
│   Flutter/Web)  │                             └────────┬─────────┘
│                 │     2. Confirm card                  │
│                 │ ─────────────────────────────────────│──> Stripe
│                 │     (using Stripe.js / SDK)          │
│                 │ <─ { status: "succeeded" } ──────────┘
└─────────────────┘
```

---

## Step-by-Step Flow

### Step 1 — Backend: Create a Payment

Your backend (or mobile app calling PayGateway) creates a payment intent:

```http
POST /api/v1/payments
X-API-Key: pgw_live_...
Idempotency-Key: order-1001-v1
Content-Type: application/json

{
  "amount": 2500,
  "currency": "USD",
  "customer_id": "user-abc123",
  "metadata": { "order_id": "1001" }
}
```

Response:
```json
{
  "id": "3fa85f64-...",
  "client_secret": "pi_3Tk4Y3DTpg7yoNvm3RDbdsdQ_secret_xyz",
  "status": "pending",
  "amount": 2500,
  "currency": "USD"
}
```

Pass `client_secret` to your frontend. **Never pass your API key to the frontend.**

---

### Step 2 — Frontend: Collect Card Details

Use Stripe's official SDK to collect card information securely. Stripe handles all PCI-DSS compliance.

#### Angular / Web (Stripe.js)

```bash
npm install @stripe/stripe-js
```

```typescript
import { loadStripe } from '@stripe/stripe-js';

const stripe = await loadStripe('pk_live_...');  // publishable key only
const elements = stripe.elements();
const cardElement = elements.create('card');
cardElement.mount('#card-element');

// When user clicks "Pay"
const { paymentMethod, error } = await stripe.createPaymentMethod({
  type: 'card',
  card: cardElement,
});

if (error) {
  // Show error to user
} else {
  // Send paymentMethod.id to your backend
  await callYourBackend('/confirm-payment', {
    paymentMethodId: paymentMethod.id,
    paymentId: payment.id,  // from Step 1
  });
}
```

#### Flutter (flutter_stripe)

```yaml
# pubspec.yaml
dependencies:
  flutter_stripe: ^10.0.0
```

```dart
import 'package:flutter_stripe/flutter_stripe.dart';

Stripe.publishableKey = 'pk_live_...';  // publishable key only

// Present card input sheet
await Stripe.instance.initPaymentSheet(
  paymentSheetParameters: SetupPaymentSheetParameters(
    paymentIntentClientSecret: clientSecret,  // from Step 1
    merchantDisplayName: 'Your Company',
  ),
);

await Stripe.instance.presentPaymentSheet();
// On success, payment is confirmed — notify your backend
```

---

### Step 3 — Backend: Confirm the Payment

After the frontend collects the card and gets a `paymentMethod.id`, your backend confirms it:

```http
POST /api/v1/payments/{payment_id}/confirm
X-API-Key: pgw_live_...
Idempotency-Key: confirm-order-1001-v1
Content-Type: application/json

{
  "payment_method_id": "pm_1AbCdEfG..."
}
```

Response:
```json
{
  "id": "3fa85f64-...",
  "status": "succeeded",
  "confirmed_at": "2026-06-19T16:00:00Z"
}
```

---

### Step 4 — Handle 3DS (if required)

Some cards require 3D Secure authentication. If `status` is `requires_action`, handle it on the frontend:

**Web:**
```typescript
const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret);
if (error) {
  // 3DS failed
} else if (paymentIntent.status === 'succeeded') {
  // Notify your backend — payment is confirmed via webhook too
}
```

**Flutter:**
```dart
// flutter_stripe handles this automatically in presentPaymentSheet()
```

After 3DS completes, Stripe sends a `payment_intent.succeeded` webhook which PayGateway processes to update the DB.

---

## Handling Payment Results

### On Success

Show a confirmation to the user. Your backend should:
1. Verify `status === "succeeded"` via `GET /api/v1/payments/{id}`
2. Fulfil the order
3. Email receipt

**Do not rely solely on the frontend to report success** — always verify server-side.

### On Failure

Check `failure_code` and `failure_message` in the payment response:

| `failure_code` | User-friendly message |
|---------------|----------------------|
| `card_declined` | Your card was declined. Please try a different card. |
| `insufficient_funds` | Insufficient funds. Please try a different card. |
| `expired_card` | Your card has expired. Please update your card details. |
| `incorrect_cvc` | Incorrect security code. Please check and try again. |
| `processing_error` | A processing error occurred. Please try again. |

---

## Refunds (Backend-Only)

Refunds are initiated server-side only — never expose refund capability to end users directly:

```http
POST /api/v1/payments/{payment_id}/refund
X-API-Key: pgw_live_...
Idempotency-Key: refund-order-1001-v1
Content-Type: application/json

{
  "amount": 1000,
  "reason": "customer_request"
}
```

---

## Angular Service Example

```typescript
// payment.service.ts
@Injectable({ providedIn: 'root' })
export class PaymentService {
  private apiUrl = 'https://your-api.example.com/api/v1';
  // API key injected server-side — Angular never holds the key
  
  createPayment(order: Order): Observable<PaymentResponse> {
    return this.http.post<PaymentResponse>(
      `${this.apiUrl}/payments`,
      { amount: order.totalCents, currency: 'USD', metadata: { orderId: order.id } },
      { headers: { 'Idempotency-Key': `create-${order.id}` } }  // your backend adds X-API-Key
    );
  }

  confirmPayment(paymentId: string, paymentMethodId: string): Observable<PaymentResponse> {
    return this.http.post<PaymentResponse>(
      `${this.apiUrl}/payments/${paymentId}/confirm`,
      { payment_method_id: paymentMethodId },
      { headers: { 'Idempotency-Key': `confirm-${paymentId}` } }
    );
  }

  getPayment(paymentId: string): Observable<PaymentResponse> {
    return this.http.get<PaymentResponse>(`${this.apiUrl}/payments/${paymentId}`);
  }
}
```

> **Note:** In a browser context, route API calls through your own backend-for-frontend (BFF) so the `X-API-Key` never appears in browser network logs. The Angular app should call your BFF, which proxies to PayGateway with the secret key.

---

## Backend-for-Frontend Pattern (Recommended)

```
Angular App  →  Your BFF / Next.js API Route  →  PayGateway
              (adds X-API-Key here)
```

This ensures:
- API keys never appear in browser DevTools → Network tab
- You can apply additional auth (user session) before calling PayGateway
- Rate limits are per-BFF-key, not per-end-user-IP

---

## Error Handling Reference

```typescript
try {
  const payment = await paymentService.createPayment(order);
} catch (err: any) {
  const code = err.error?.detail?.error?.code;
  switch (code) {
    case 'RATE_LIMITED':
      // Show "Too many requests, please wait"
      break;
    case 'PROVIDER_ERROR':
      // Stripe-side issue, show "Payment processor unavailable"
      break;
    case 'IDEMPOTENCY_KEY_MISSING':
      // Bug in your client — missing header
      break;
    default:
      // Generic error
  }
}
```
