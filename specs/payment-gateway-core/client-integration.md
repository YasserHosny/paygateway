# Payment Gateway Core Service — Client Integration Guide

## 1. Overview

This guide describes how different client platforms integrate with the Payment Gateway Core Service. All clients interact via the REST API — no client should implement payment business logic.

## 2. General Integration Pattern

All client integrations follow this pattern:

```
[Client App] ──POST /api/v1/payments──> [Payment Gateway] ──> [Stripe]
                                              |
                                              v
[Client App] <──{payment_id, client_secret}───┘
      |
      v
[Stripe SDK] ──confirm with client_secret──> [Stripe]
      |
      v
[Stripe] ──webhook──> [Payment Gateway] (status update)
      |
      v
[Client App] ──GET /api/v1/payments/{id}──> [Payment Gateway] (poll for status)
```

## 3. Angular Web Integration

### 3.1 Prerequisites

- Install `@stripe/stripe-js` package.
- Obtain the Stripe publishable key from backend config or environment.
- Authenticate with the Payment Gateway (JWT or API key depending on architecture).

### 3.2 Payment Flow

#### Step 1: Create Payment Intent (Backend Call)

```typescript
// payment.service.ts
@Injectable({ providedIn: 'root' })
export class PaymentService {
  constructor(private http: HttpClient) {}

  createPayment(request: CreatePaymentRequest): Observable<PaymentResponse> {
    return this.http.post<PaymentResponse>('/api/v1/payments', request, {
      headers: {
        'Idempotency-Key': this.generateIdempotencyKey(),
      },
    });
  }

  getPaymentStatus(paymentId: string): Observable<PaymentResponse> {
    return this.http.get<PaymentResponse>(`/api/v1/payments/${paymentId}`);
  }

  private generateIdempotencyKey(): string {
    return `web_${crypto.randomUUID()}`;
  }
}
```

#### Step 2: Confirm Payment (Client-Side Stripe)

```typescript
// checkout.component.ts
import { loadStripe, Stripe } from '@stripe/stripe-js';

export class CheckoutComponent implements OnInit {
  private stripe: Stripe | null = null;

  async ngOnInit() {
    this.stripe = await loadStripe('pk_test_...');
  }

  async onSubmit() {
    // 1. Create payment intent via backend
    const payment = await firstValueFrom(
      this.paymentService.createPayment({
        amount: 5000,
        currency: 'usd',
        customer_id: this.currentUser.id,
        metadata: { order_id: this.orderId },
      })
    );

    // 2. Confirm with Stripe.js
    const { error, paymentIntent } = await this.stripe!.confirmPayment({
      clientSecret: payment.client_secret,
      elements: this.paymentElements,  // Stripe Elements instance
      confirmParams: {
        return_url: `${window.location.origin}/payment/result`,
      },
    });

    if (error) {
      this.handleError(error);
    }
    // On success, user is redirected to return_url
    // Backend receives webhook and updates status
  }
}
```

#### Step 3: Check Result (After Redirect)

```typescript
// payment-result.component.ts
export class PaymentResultComponent implements OnInit {
  async ngOnInit() {
    const paymentId = this.route.snapshot.queryParamMap.get('payment_id');
    // Poll for final status
    this.paymentService.getPaymentStatus(paymentId!).subscribe(payment => {
      this.paymentStatus = payment.status;
    });
  }
}
```

### 3.3 Security Rules for Angular

- Never include `STRIPE_SECRET_KEY` in Angular code or environment files.
- Only use the publishable key (`pk_test_...` / `pk_live_...`).
- Never call Stripe's server-side APIs from Angular.
- Always create PaymentIntents via the backend API.
- Use Stripe Elements for card input (never raw input fields).

## 4. Flutter Mobile Integration

### 4.1 Prerequisites

- Add `flutter_stripe` package to `pubspec.yaml`.
- Add `http` or `dio` package for API calls.
- Initialize Stripe with publishable key at app startup.

### 4.2 Payment Flow

#### Step 1: Initialize Stripe

```dart
// main.dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  Stripe.publishableKey = 'pk_test_...';
  // Optionally set merchant identifier for Apple Pay
  // Stripe.merchantIdentifier = 'merchant.com.example';
  runApp(MyApp());
}
```

#### Step 2: Create Payment Intent (Backend Call)

```dart
// payment_service.dart
class PaymentService {
  final String baseUrl;
  final String apiKey;

  PaymentService({required this.baseUrl, required this.apiKey});

  Future<PaymentResponse> createPayment({
    required int amount,
    required String currency,
    String? customerId,
    Map<String, String>? metadata,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/payments'),
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
        'Idempotency-Key': 'mobile_${Uuid().v4()}',
      },
      body: jsonEncode({
        'amount': amount,
        'currency': currency,
        'customer_id': customerId,
        'metadata': metadata,
      }),
    );
    return PaymentResponse.fromJson(jsonDecode(response.body));
  }
}
```

#### Step 3: Confirm Payment (Client-Side Stripe)

```dart
// checkout_screen.dart
Future<void> processPayment() async {
  // 1. Create payment intent via backend
  final payment = await paymentService.createPayment(
    amount: 5000,
    currency: 'usd',
    customerId: currentUser.id,
  );

  // 2. Initialize payment sheet
  await Stripe.instance.initPaymentSheet(
    paymentSheetParameters: SetupPaymentSheetParameters(
      paymentIntentClientSecret: payment.clientSecret,
      merchantDisplayName: 'Your App Name',
    ),
  );

  // 3. Present payment sheet
  await Stripe.instance.presentPaymentSheet();

  // 4. Poll for confirmation
  final result = await paymentService.getPaymentStatus(payment.id);
  // Handle result
}
```

### 4.3 Security Rules for Flutter

- Never embed `STRIPE_SECRET_KEY` in the app binary.
- Only use the publishable key.
- Store API keys securely (flutter_secure_storage, not SharedPreferences).
- Pin SSL certificates for API calls in production.
- Use Stripe's payment sheet UI — never custom card input fields.

## 5. Generic REST API Client

For desktop apps, server-to-server, or third-party integrations.

### 5.1 Authentication

```
X-API-Key: pgw_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456
```

### 5.2 Payment Creation

```bash
curl -X POST https://api.example.com/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: pgw_live_..." \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "amount": 5000,
    "currency": "usd",
    "customer_id": "user_123",
    "description": "Order #456"
  }'
```

### 5.3 Status Polling

```bash
curl https://api.example.com/api/v1/payments/{payment_id} \
  -H "X-API-Key: pgw_live_..."
```

### 5.4 Refund

```bash
curl -X POST https://api.example.com/api/v1/payments/{payment_id}/refund \
  -H "Content-Type: application/json" \
  -H "X-API-Key: pgw_live_..." \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "amount": 2500,
    "reason": "Customer request"
  }'
```

## 6. Server-to-Server Integration

For cases where the calling service handles payment method collection itself (e.g., using a previously saved payment method).

```
[Calling Service] ──POST /payments──> [Payment Gateway] ──> [Stripe]
[Calling Service] ──POST /payments/{id}/confirm──> [Payment Gateway] ──> [Stripe]
[Payment Gateway] ──webhook──> [Status Update]
[Calling Service] ──GET /payments/{id}──> [Payment Gateway]
```

The `/confirm` endpoint accepts a `payment_method_id` for server-side confirmation without client involvement.

## 7. Idempotency Key Best Practices

- Generate a unique key per payment attempt (UUID v4 recommended).
- Prefix with client type for debugging: `web_`, `mobile_`, `api_`, `svc_`.
- Store the key alongside the order/transaction on the client side.
- If retrying a failed request, reuse the same key.
- Never reuse keys across different payment operations.

## 8. Error Handling

All clients should handle these error scenarios:

| HTTP Status | Action |
|-------------|--------|
| 400 | Show validation error to user |
| 401 | Redirect to login / refresh token |
| 403 | Show permission denied message |
| 404 | Payment not found — show appropriate message |
| 409 | Conflict (e.g., already refunded) — refresh state |
| 422 | Idempotency mismatch — generate new key and retry |
| 429 | Rate limited — wait and retry (use Retry-After header) |
| 500 | Server error — show generic error, log details |
| 502/503 | Provider error — show temporary error, suggest retry |
