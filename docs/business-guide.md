# Business Guide

## What Does This Solve?

Every business that accepts online payments faces the same set of problems:

1. **PCI compliance** — storing or transmitting raw card numbers is risky and expensive
2. **Auditability** — knowing exactly what happened and when, for disputes and chargebacks
3. **Multi-client access** — giving your mobile app, web app, and backend different levels of access
4. **Operational resilience** — reconciling what Stripe recorded vs what your DB shows
5. **Vendor lock-in risk** — if you ever switch from Stripe, you want a clean abstraction

PayGateway addresses all five.

---

## Business Flows Supported

### Standard Purchase

A customer buys a product on your website or app:

1. Customer fills cart → your backend calls `POST /api/v1/payments` ($25.00)
2. Customer enters card details in Stripe's UI → Stripe.js returns a payment method token
3. Your backend calls `POST /api/v1/payments/{id}/confirm` → charge processed
4. Order fulfilled, receipt sent

**Result:** Payment recorded in your DB with full audit trail.

### Subscription / Recurring Billing

For recurring charges, create a payment intent per billing cycle. Stripe's customer ID can be stored in `customer_id` for future lookups.

### Partial Refund (Customer Service)

A customer received a damaged item and requests a partial refund ($10 of $25 paid):

1. CS agent triggers `POST /api/v1/payments/{id}/refund` with `amount: 1000`
2. Stripe processes the refund (usually within minutes)
3. `refunded_amount` on the payment updates; status becomes `partially_refunded`

### Full Refund / Return

Same as above without specifying `amount` — the entire remaining balance is refunded.

### Abandoned Cart / Order Cancellation

Customer abandons checkout before card confirmation:

1. `POST /api/v1/payments/{id}/cancel` marks the intent as canceled
2. No charge was ever made — no financial impact
3. Stripe releases the hold on the card

---

## Financial Reconciliation

At the end of each business day (or on-demand), PayGateway compares its records against Stripe:

- Every payment in your DB is checked against its Stripe counterpart
- Mismatches (e.g. DB says `pending` but Stripe says `succeeded`) are flagged
- Reports are stored and queryable via `GET /api/v1/admin/reconciliation/reports`

**Why this matters:** Payment webhooks can fail or arrive out of order. Reconciliation is the safety net that catches any DB/Stripe drift.

---

## Chargeback & Dispute Support

When a customer disputes a charge with their bank:

1. Stripe sends a dispute webhook event
2. Pull the full payment record: `GET /api/v1/payments/{id}`
3. Pull the audit log from your DB — every action timestamped with actor and IP
4. Pull the `metadata` — your internal order ID, customer ID, channel
5. Submit evidence to Stripe with this complete paper trail

The audit log is tamper-proof (write-once) — it's valuable evidence in disputes.

---

## Multi-Currency

PayGateway supports any currency Stripe accepts. Amounts are always in the **smallest currency unit**:

| Currency | Smallest Unit | Example |
|----------|--------------|---------|
| USD | cents | $25.00 = `2500` |
| EUR | euro cents | €10.00 = `1000` |
| JPY | yen (no subdivision) | ¥1000 = `1000` |
| KWD | fils (3 decimal places) | KWD 1.000 = `1000` |

Filter payments by currency: `GET /api/v1/payments?currency=EUR`

---

## Access Control for Teams

Different team members get different roles:

| Team | Role | What They Can Do |
|------|------|-----------------|
| Backend service | `service` | Create and confirm payments, cancel payments |
| Finance team | `readonly` | View payments and refunds, run reports |
| Admin / CS | `admin` | Everything including refunds and reconciliation |

Each role gets its own API key. Revoke a key instantly by setting `is_active = false`.

---

## Operational Visibility

### Key Metrics Available

Query your DB directly for business intelligence:

```sql
-- Revenue today (USD)
SELECT SUM(amount) / 100.0 as revenue_usd
FROM payments
WHERE currency = 'USD'
  AND status = 'succeeded'
  AND created_at >= CURRENT_DATE;

-- Refund rate this month
SELECT 
  COUNT(CASE WHEN status = 'succeeded' THEN 1 END) as successful,
  COUNT(CASE WHEN status IN ('partially_refunded','refunded') THEN 1 END) as refunded
FROM payments
WHERE created_at >= date_trunc('month', CURRENT_DATE);

-- Failed payments by failure code
SELECT failure_code, COUNT(*) 
FROM payments 
WHERE status = 'failed'
GROUP BY failure_code
ORDER BY COUNT(*) DESC;
```

### Uptime Monitoring

The `/health` endpoint returns `{"status":"healthy"}` when the DB is reachable. Hook this into:
- AWS ALB health checks
- Datadog / New Relic / Uptime Robot
- PagerDuty on-call alerts

---

## Cost Considerations

PayGateway adds no fees. Your costs are:

| Cost | Who Charges | Notes |
|------|------------|-------|
| Stripe processing | Stripe | ~2.9% + $0.30 per transaction (varies by plan) |
| Stripe refunds | Stripe | No fee, but the original processing fee is not returned |
| Database (Supabase) | Supabase | Free tier supports moderate volume; Pro plan for production |
| Hosting | Your infrastructure | Single Docker container is sufficient for most loads |

---

## Scaling Considerations

| Load Level | Recommendation |
|-----------|---------------|
| < 100 req/min | Single instance, in-memory rate limiter |
| 100–1000 req/min | Single instance, Redis-backed rate limiter |
| 1000+ req/min | Multiple instances behind load balancer, Redis rate limiter, connection pooling tuned |

The DB connection pool is configured for 10 connections + 20 overflow. For high volume, upgrade to PgBouncer or Supabase's pooler in transaction mode.

---

## Integration Timeline

| Phase | Duration | Activities |
|-------|----------|-----------|
| **Setup** | 1 day | Deploy container, run migrations, configure Stripe webhook |
| **Test integration** | 1-2 days | Integrate frontend (Angular/Flutter), test full flow in Stripe test mode |
| **Go live** | 1 day | Swap test keys for live keys, run smoke test, monitor for 24h |
| **Ongoing** | Continuous | Monitor `/health`, review reconciliation reports weekly |
