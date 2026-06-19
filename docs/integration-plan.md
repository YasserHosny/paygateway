# Integration Plan

A step-by-step guide for embedding PayGateway into any platform.  
Follow **Phase 0 → Phase 1 → your platform section → Phase 4**.

---

## How PayGateway Fits In

```
┌──────────────────────────────────────────────────────────────────┐
│                        Your Platform                             │
│                                                                  │
│  ┌──────────────┐   API call    ┌────────────────────────────┐   │
│  │  Client App  │ ────────────> │  Your Backend / BFF        │   │
│  │  (Web/Mobile)│ <──────────── │  (holds X-API-Key secret)  │   │
│  └──────────────┘               └────────────┬───────────────┘   │
│                                              │                   │
└──────────────────────────────────────────────│───────────────────┘
                                               │ X-API-Key
                                               ▼
                                  ┌────────────────────────┐
                                  │    PayGateway API      │
                                  │  /api/v1/payments      │
                                  └────────────┬───────────┘
                                               │
                                               ▼
                                         ┌──────────┐
                                         │  Stripe  │
                                         └──────────┘
```

**Key rule:** `X-API-Key` lives only in your backend. Client apps receive only the payment's `client_secret`, which is scoped to a single payment intent and cannot create new charges.

---

## Phase 0 — Prerequisites (All Platforms)

Before writing any integration code, complete these steps once.

### 0.1 Deploy PayGateway
- [ ] Server running and reachable (see [Deployment Guide](deployment.md))
- [ ] `GET https://your-gateway.com/health` returns `{"status":"healthy"}`
- [ ] Database migrations applied (`alembic upgrade head`)

### 0.2 Configure Stripe
- [ ] Stripe account created at [dashboard.stripe.com](https://dashboard.stripe.com)
- [ ] Test mode keys copied into PayGateway `.env`:
  - `STRIPE_SECRET_KEY=sk_test_...`
  - `STRIPE_PUBLISHABLE_KEY=pk_test_...`
- [ ] Webhook endpoint registered in Stripe dashboard → URL: `https://your-gateway.com/api/v1/webhooks/stripe`
- [ ] `STRIPE_WEBHOOK_SECRET=whsec_...` set in `.env`

### 0.3 Create API Keys
Create at least two API keys in the database:

| Key | Role | Used By |
|-----|------|---------|
| `pgw_live_<backend>` | `service` | Your backend / BFF |
| `pgw_live_<admin>` | `admin` | Internal admin tools only |

See [Authentication Guide](authentication.md) for key creation instructions.

### 0.4 Secrets Checklist
- [ ] `JWT_SECRET_KEY` — random 64-char hex string
- [ ] `API_KEY_SALT` — random 32-char hex string
- [ ] `ALLOWED_ORIGINS` — set to your actual frontend domains
- [ ] `.env` not committed to version control

---

## Phase 1 — Backend Integration (All Platforms)

Your backend is the bridge between the client and PayGateway. This phase is **identical regardless of client platform**.

### 1.1 Create Payment Endpoint

Expose an endpoint on your backend that creates a payment via PayGateway:

```
POST /your-backend/payments/create
```

**What it does:**
1. Receives order details from the client (amount, currency, order ID)
2. Calls `POST /api/v1/payments` on PayGateway with `X-API-Key`
3. Returns `{ paymentId, clientSecret }` to the client

**Node.js / Express example:**
```javascript
app.post('/payments/create', async (req, res) => {
  const { amount, currency, orderId } = req.body;

  const response = await fetch('https://your-gateway.com/api/v1/payments', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.PAYGATEWAY_API_KEY,   // never expose this to client
      'Idempotency-Key': `create-${orderId}`,
    },
    body: JSON.stringify({ amount, currency, metadata: { order_id: orderId } }),
  });

  const payment = await response.json();
  res.json({ paymentId: payment.id, clientSecret: payment.client_secret });
});
```

**Python / FastAPI example:**
```python
@app.post("/payments/create")
async def create_payment(order: OrderRequest):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://your-gateway.com/api/v1/payments",
            json={"amount": order.amount, "currency": order.currency,
                  "metadata": {"order_id": order.order_id}},
            headers={
                "X-API-Key": settings.PAYGATEWAY_API_KEY,
                "Idempotency-Key": f"create-{order.order_id}",
            },
        )
    payment = r.json()
    return {"payment_id": payment["id"], "client_secret": payment["client_secret"]}
```

### 1.2 Confirm Payment Endpoint

```
POST /your-backend/payments/confirm
```

**What it does:**
1. Receives `paymentId` and `paymentMethodId` from the client
2. Calls `POST /api/v1/payments/{id}/confirm` on PayGateway
3. Returns updated payment status to the client

```javascript
app.post('/payments/confirm', async (req, res) => {
  const { paymentId, paymentMethodId, orderId } = req.body;

  const response = await fetch(
    `https://your-gateway.com/api/v1/payments/${paymentId}/confirm`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': process.env.PAYGATEWAY_API_KEY,
        'Idempotency-Key': `confirm-${orderId}`,
      },
      body: JSON.stringify({ payment_method_id: paymentMethodId }),
    }
  );

  const result = await response.json();
  res.json({ status: result.status });
});
```

### 1.3 Verify Payment Status (Server-Side)

**Never trust the client to report payment success.** Always verify:

```javascript
app.get('/payments/:id/status', async (req, res) => {
  const response = await fetch(
    `https://your-gateway.com/api/v1/payments/${req.params.id}`,
    { headers: { 'X-API-Key': process.env.PAYGATEWAY_API_KEY } }
  );
  const payment = await response.json();

  if (payment.status === 'succeeded') {
    await fulfillOrder(payment.metadata.order_id);
  }

  res.json({ status: payment.status });
});
```

### 1.4 Webhook Handler

Register a webhook receiver on your backend so Stripe events update your system automatically:

```javascript
app.post('/webhooks/payment-update', express.raw({ type: 'application/json' }), async (req, res) => {
  // PayGateway already verified the Stripe signature.
  // This is YOUR webhook from PayGateway (optional — for custom business logic).
  // Alternatively, rely on polling GET /payments/{id} after client confirms.
  res.sendStatus(200);
});
```

> PayGateway itself handles the Stripe webhook at `/api/v1/webhooks/stripe` and keeps its DB in sync. You only need your own webhook handler if you want to trigger additional business logic (send emails, update order state, etc.).

---

## Phase 2 — Platform Integration

Choose your client platform:

- [Web App (React / Next.js)](#web-app--react--nextjs)
- [Web App (Angular)](#web-app--angular)
- [Web App (Vue.js)](#web-app--vuejs)
- [Mobile (Flutter)](#mobile--flutter)
- [Mobile (React Native)](#mobile--react-native)
- [Mobile (iOS — Swift)](#mobile--ios--swift)
- [Mobile (Android — Kotlin)](#mobile--android--kotlin)
- [Backend Service (server-to-server)](#backend-service--server-to-server)

---

### Web App — React / Next.js

**Dependencies:**
```bash
npm install @stripe/stripe-js @stripe/react-stripe-js
```

**Setup (once in your app root):**
```tsx
// app/layout.tsx or _app.tsx
import { Elements } from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/stripe-js';

const stripePromise = loadStripe('pk_live_...');  // publishable key only

export default function RootLayout({ children }) {
  return <Elements stripe={stripePromise}>{children}</Elements>;
}
```

**Checkout component:**
```tsx
import { CardElement, useStripe, useElements } from '@stripe/react-stripe-js';

export function CheckoutForm({ orderId, amount }: { orderId: string; amount: number }) {
  const stripe = useStripe();
  const elements = useElements();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Step 1: Create payment via your backend
    const { paymentId, clientSecret } = await fetch('/api/payments/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount, currency: 'USD', orderId }),
    }).then(r => r.json());

    // Step 2: Collect card → get payment method
    const { paymentMethod, error } = await stripe!.createPaymentMethod({
      type: 'card',
      card: elements!.getElement(CardElement)!,
    });
    if (error) { alert(error.message); return; }

    // Step 3: Confirm via your backend
    const { status } = await fetch('/api/payments/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paymentId, paymentMethodId: paymentMethod.id, orderId }),
    }).then(r => r.json());

    if (status === 'succeeded') {
      // redirect to success page
    } else if (status === 'requires_action') {
      // handle 3DS
      await stripe!.confirmCardPayment(clientSecret);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <CardElement />
      <button type="submit">Pay</button>
    </form>
  );
}
```

**Next.js API routes (BFF):**
```typescript
// app/api/payments/create/route.ts
export async function POST(req: Request) {
  const { amount, currency, orderId } = await req.json();
  const res = await fetch(`${process.env.PAYGATEWAY_URL}/api/v1/payments`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.PAYGATEWAY_API_KEY!,
      'Idempotency-Key': `create-${orderId}`,
    },
    body: JSON.stringify({ amount, currency, metadata: { order_id: orderId } }),
  });
  const payment = await res.json();
  return Response.json({ paymentId: payment.id, clientSecret: payment.client_secret });
}
```

**Integration checklist:**
- [ ] `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` set (public env var — safe in browser)
- [ ] `PAYGATEWAY_API_KEY` set (server env var — never exposed to browser)
- [ ] BFF routes created for create and confirm
- [ ] 3DS flow handled via `stripe.confirmCardPayment(clientSecret)`
- [ ] Success and failure states handled in UI

---

### Web App — Angular

**Dependencies:**
```bash
npm install @stripe/stripe-js
```

**Service:**
```typescript
// payment.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { loadStripe, Stripe } from '@stripe/stripe-js';
import { firstValueFrom } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class PaymentService {
  private bffUrl = '/api';  // your BFF — never call PayGateway directly from Angular
  private stripe: Stripe | null = null;

  constructor(private http: HttpClient) {
    loadStripe(environment.stripePublishableKey).then(s => this.stripe = s);
  }

  async pay(orderId: string, amount: number, currency: string): Promise<string> {
    // 1. Create payment (through your BFF)
    const { paymentId, clientSecret } = await firstValueFrom(
      this.http.post<any>(`${this.bffUrl}/payments/create`,
        { orderId, amount, currency })
    );

    // 2. Collect card
    const elements = this.stripe!.elements();
    const card = elements.create('card');
    card.mount('#card-element');
    const { paymentMethod, error } = await this.stripe!.createPaymentMethod({ type: 'card', card });
    if (error) throw error;

    // 3. Confirm (through your BFF)
    const { status } = await firstValueFrom(
      this.http.post<any>(`${this.bffUrl}/payments/confirm`,
        { paymentId, paymentMethodId: paymentMethod!.id, orderId })
    );

    if (status === 'requires_action') {
      await this.stripe!.confirmCardPayment(clientSecret);
    }

    return status;
  }
}
```

**Integration checklist:**
- [ ] `environment.stripePublishableKey` set in `environment.ts`
- [ ] `HttpClientModule` imported
- [ ] BFF (Node.js / .NET / Python) proxies calls with `X-API-Key`
- [ ] Card element mounted to DOM before calling `createPaymentMethod`

---

### Web App — Vue.js

**Dependencies:**
```bash
npm install @stripe/stripe-js
```

**Composable:**
```typescript
// composables/usePayment.ts
import { loadStripe } from '@stripe/stripe-js';

export function usePayment() {
  const stripe = await loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

  async function pay(orderId: string, amount: number, currency: string) {
    // 1. Create via BFF
    const { paymentId, clientSecret } = await fetch('/api/payments/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId, amount, currency }),
    }).then(r => r.json());

    // 2. Collect card
    const elements = stripe!.elements();
    const card = elements.create('card');
    card.mount('#card-element');
    const { paymentMethod, error } = await stripe!.createPaymentMethod({ type: 'card', card });
    if (error) throw error;

    // 3. Confirm via BFF
    const { status } = await fetch('/api/payments/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paymentId, paymentMethodId: paymentMethod!.id, orderId }),
    }).then(r => r.json());

    if (status === 'requires_action') await stripe!.confirmCardPayment(clientSecret);
    return status;
  }

  return { pay };
}
```

**Integration checklist:**
- [ ] `VITE_STRIPE_PUBLISHABLE_KEY` in `.env` (public — safe)
- [ ] BFF (Nuxt server routes or separate backend) holds `X-API-Key`
- [ ] `#card-element` div present in template before mounting

---

### Mobile — Flutter

**Dependencies (`pubspec.yaml`):**
```yaml
dependencies:
  flutter_stripe: ^10.0.0
  http: ^1.2.0
```

**Initialization (`main.dart`):**
```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  Stripe.publishableKey = 'pk_live_...';  // publishable key only
  await Stripe.instance.applySettings();
  runApp(MyApp());
}
```

**Payment flow:**
```dart
class PaymentService {
  final String _bffUrl = 'https://your-backend.com';

  Future<void> pay({
    required String orderId,
    required int amount,
    required String currency,
  }) async {
    // Step 1: Create payment via your backend
    final createRes = await http.post(
      Uri.parse('$_bffUrl/payments/create'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'orderId': orderId, 'amount': amount, 'currency': currency}),
    );
    final data = jsonDecode(createRes.body);
    final clientSecret = data['clientSecret'] as String;

    // Step 2 & 3: Stripe Payment Sheet (handles card collection + confirm + 3DS)
    await Stripe.instance.initPaymentSheet(
      paymentSheetParameters: SetupPaymentSheetParameters(
        paymentIntentClientSecret: clientSecret,
        merchantDisplayName: 'Your Company',
        style: ThemeMode.system,
      ),
    );
    await Stripe.instance.presentPaymentSheet();

    // Step 4: Verify server-side
    final statusRes = await http.get(
      Uri.parse('$_bffUrl/payments/${data['paymentId']}/status'),
    );
    final status = jsonDecode(statusRes.body)['status'];
    if (status != 'succeeded') throw Exception('Payment failed: $status');
  }
}
```

**Integration checklist:**
- [ ] `flutter_stripe` added to `pubspec.yaml`
- [ ] `Stripe.publishableKey` set at app startup (publishable key only)
- [ ] Backend (`_bffUrl`) creates and confirms via PayGateway with `X-API-Key`
- [ ] `presentPaymentSheet()` handles card input, 3DS, and error display automatically
- [ ] iOS: `NSAppTransportSecurity` configured in `Info.plist`
- [ ] Android: `minSdkVersion 21` in `build.gradle`

---

### Mobile — React Native

**Dependencies:**
```bash
npm install @stripe/stripe-react-native
npx pod-install  # iOS only
```

**Setup:**
```tsx
// App.tsx
import { StripeProvider } from '@stripe/stripe-react-native';

export default function App() {
  return (
    <StripeProvider publishableKey="pk_live_...">
      <Navigator />
    </StripeProvider>
  );
}
```

**Payment hook:**
```tsx
import { useStripe } from '@stripe/stripe-react-native';

export function usePayment() {
  const { initPaymentSheet, presentPaymentSheet } = useStripe();

  async function pay(orderId: string, amount: number, currency: string) {
    // Step 1: Create via your backend
    const res = await fetch('https://your-backend.com/payments/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId, amount, currency }),
    });
    const { paymentId, clientSecret } = await res.json();

    // Step 2: Init payment sheet
    const { error: initError } = await initPaymentSheet({
      paymentIntentClientSecret: clientSecret,
      merchantDisplayName: 'Your Company',
    });
    if (initError) throw initError;

    // Step 3: Present sheet (handles card + 3DS)
    const { error: presentError } = await presentPaymentSheet();
    if (presentError) throw presentError;

    // Step 4: Verify server-side
    const statusRes = await fetch(`https://your-backend.com/payments/${paymentId}/status`);
    const { status } = await statusRes.json();
    return status;
  }

  return { pay };
}
```

**Integration checklist:**
- [ ] `@stripe/stripe-react-native` installed and pods linked
- [ ] `StripeProvider` wraps root component with publishable key
- [ ] iOS: `NSAppTransportSecurity` in `Info.plist`; `pod install` run
- [ ] Android: `minSdkVersion 21`; `implementation "com.stripe:stripe-android:..."` if needed
- [ ] Backend holds `X-API-Key` — never in the RN app

---

### Mobile — iOS (Swift / SwiftUI)

**Dependencies (`Package.swift` or SPM):**
```
https://github.com/stripe/stripe-ios — version ≥ 23.0.0
```

**Setup (`AppDelegate.swift`):**
```swift
import StripeCore

@main
struct MyApp: App {
    init() {
        StripeAPI.defaultPublishableKey = "pk_live_..."  // publishable key only
    }
    var body: some Scene { WindowGroup { ContentView() } }
}
```

**Payment view:**
```swift
import StripePaymentSheet

class PaymentViewModel: ObservableObject {
    var paymentSheet: PaymentSheet?

    func prepare(orderId: String, amount: Int, currency: String) async throws {
        // Step 1: Create via your backend
        let url = URL(string: "https://your-backend.com/payments/create")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "orderId": orderId, "amount": amount, "currency": currency
        ])
        let (data, _) = try await URLSession.shared.data(for: req)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let clientSecret = json["clientSecret"] as! String

        // Step 2: Configure Payment Sheet
        var config = PaymentSheet.Configuration()
        config.merchantDisplayName = "Your Company"
        paymentSheet = PaymentSheet(paymentIntentClientSecret: clientSecret, configuration: config)
    }

    func present(from vc: UIViewController) {
        paymentSheet?.present(from: vc) { result in
            switch result {
            case .completed: print("Payment succeeded")
            case .failed(let error): print("Payment failed: \(error)")
            case .canceled: print("Payment canceled")
            }
        }
    }
}
```

**Integration checklist:**
- [ ] Stripe iOS SDK added via SPM
- [ ] `StripeAPI.defaultPublishableKey` set at app launch
- [ ] Backend returns `clientSecret` (your backend holds the `X-API-Key`)
- [ ] `PaymentSheet` used for card collection — never collect raw card numbers
- [ ] `NSAppTransportSecurity` in `Info.plist` for localhost dev (remove in production)

---

### Mobile — Android (Kotlin)

**Dependencies (`build.gradle`):**
```gradle
implementation 'com.stripe:stripe-android:20.+'
```

**Setup (`Application.kt`):**
```kotlin
class MyApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        PaymentConfiguration.init(applicationContext, "pk_live_...")  // publishable key only
    }
}
```

**Payment flow:**
```kotlin
class CheckoutViewModel(private val backendUrl: String) : ViewModel() {

    suspend fun pay(orderId: String, amount: Int, currency: String): PaymentSheetResult {
        // Step 1: Create via your backend
        val response = apiClient.post("$backendUrl/payments/create") {
            body = mapOf("orderId" to orderId, "amount" to amount, "currency" to currency)
        }
        val clientSecret = response["clientSecret"] as String
        val paymentId = response["paymentId"] as String

        return suspendCoroutine { cont ->
            val paymentSheet = PaymentSheet(fragment) { result ->
                cont.resume(result)
            }
            // Step 2: Present sheet (handles card input + confirm + 3DS)
            paymentSheet.presentWithPaymentIntent(
                clientSecret,
                PaymentSheet.Configuration(merchantDisplayName = "Your Company")
            )
        }
    }
}
```

**Integration checklist:**
- [ ] `stripe-android` dependency added
- [ ] `PaymentConfiguration.init()` called in `Application.onCreate()`
- [ ] `minSdkVersion 21` in `build.gradle`
- [ ] Backend holds `X-API-Key` — never in the APK
- [ ] `PaymentSheet` used — Stripe handles PCI compliance
- [ ] ProGuard / R8 rules added if minifying (Stripe provides these)

---

### Backend Service (Server-to-Server)

For machine-to-machine payments (e.g. subscription billing, automated invoicing) where there is no human card-entry step:

```python
# Python example — direct server-to-server
import httpx, uuid

PAYGATEWAY_URL = "https://your-gateway.com"
API_KEY = "pgw_live_..."  # from environment variable

async def charge_subscription(customer_id: str, payment_method_id: str, amount: int):
    order_id = str(uuid.uuid4())
    async with httpx.AsyncClient() as client:
        # 1. Create payment
        r = await client.post(f"{PAYGATEWAY_URL}/api/v1/payments",
            json={"amount": amount, "currency": "USD",
                  "customer_id": customer_id, "metadata": {"type": "subscription"}},
            headers={"X-API-Key": API_KEY, "Idempotency-Key": f"sub-{order_id}"},
        )
        payment = r.json()

        # 2. Confirm with stored payment method
        r = await client.post(
            f"{PAYGATEWAY_URL}/api/v1/payments/{payment['id']}/confirm",
            json={"payment_method_id": payment_method_id},
            headers={"X-API-Key": API_KEY, "Idempotency-Key": f"conf-{order_id}"},
        )
        result = r.json()

    if result["status"] != "succeeded":
        raise Exception(f"Payment failed: {result.get('failure_code')}")
    return result["id"]
```

> For stored payment methods, use Stripe's setup intent flow to save a customer's card for future use, then pass the saved `pm_...` ID to the confirm call.

---

## Phase 3 — Testing (All Platforms)

Before going to production, validate the full flow end-to-end in test mode.

### Test Credentials

| Item | Value |
|------|-------|
| Stripe secret key | `sk_test_...` |
| Stripe publishable key | `pk_test_...` |
| Test Visa (always succeeds) | Card: `4242 4242 4242 4242`, Exp: `12/34`, CVC: `123` |
| Test card (3DS required) | `4000 0025 0000 3155` |
| Test card (always declined) | `4000 0000 0000 9995` |
| Server-side test PM | `pm_card_visa` (no card number needed) |

### Per-Platform Test Checklist

- [ ] Create payment → response contains `client_secret`
- [ ] Card collected via Stripe SDK (no raw card data in your app)
- [ ] Payment confirmed → status `succeeded`
- [ ] GET payment → status `succeeded`, `refunded_amount: 0`
- [ ] Decline scenario handled gracefully in UI
- [ ] 3DS scenario triggers Stripe's authentication UI
- [ ] Refund initiated from admin panel → status `succeeded`
- [ ] Idempotency: retry same request → same payment ID returned
- [ ] No `X-API-Key` visible in client network logs / APK strings

---

## Phase 4 — Go Live

### Pre-Launch Checklist

- [ ] Switch from `sk_test_` / `pk_test_` to live keys (`sk_live_` / `pk_live_`)
- [ ] Update `STRIPE_WEBHOOK_SECRET` to the live webhook signing secret
- [ ] `ENVIRONMENT=production` in PayGateway `.env`
- [ ] TLS certificate on your gateway domain
- [ ] `ALLOWED_ORIGINS` set to production frontend URLs only
- [ ] Rate limits reviewed for expected traffic (see [API Reference](api-reference.md))
- [ ] Run one real test transaction (small amount, real card) before full launch
- [ ] Monitor `/health` endpoint in your uptime tool
- [ ] Set up alerts on Stripe dashboard for payment failures and disputes

### Post-Launch

| Task | Frequency |
|------|-----------|
| Review reconciliation reports | Weekly |
| Check audit log for anomalies | Weekly |
| Rotate API keys | Every 90 days |
| Review failed payments report | Daily |
| Update Stripe SDK in dependencies | Monthly |

---

## Quick Reference — API Calls Summary

| Step | Method | Endpoint | Who Calls It |
|------|--------|----------|-------------|
| Create | `POST` | `/api/v1/payments` | Your backend |
| Confirm | `POST` | `/api/v1/payments/{id}/confirm` | Your backend |
| Check status | `GET` | `/api/v1/payments/{id}` | Your backend |
| Refund | `POST` | `/api/v1/payments/{id}/refund` | Your backend (admin) |
| List payments | `GET` | `/api/v1/payments` | Your backend |
| Health check | `GET` | `/health` | Load balancer / monitoring |

All calls require `X-API-Key` header. All `POST` calls require `Idempotency-Key` header.

---

## Related Documents

| Document | Description |
|----------|-------------|
| [API Reference](api-reference.md) | Full endpoint reference with request/response schemas |
| [Authentication](authentication.md) | API key creation, JWT, roles |
| [Webhooks](webhooks.md) | Stripe webhook setup and event handling |
| [Security](security.md) | Security model and production checklist |
| [Testing Guide](testing-guide.md) | Test cards, test suite, validation scripts |
