# Payment Gateway Core Service — Reconciliation Design

## 1. Purpose

Reconciliation ensures that the internal payment database is consistent with the payment provider's (Stripe's) records. It detects:

- Payments that exist internally but not at the provider (or vice versa).
- Amount mismatches between internal and provider records.
- Status mismatches.
- Currency mismatches.

## 2. Reconciliation Flow

```
[Trigger: Manual API call or Scheduled Job]
        |
        v
[1. Fetch Internal Records for Date Range]
        |
        v
[2. Fetch Provider Records for Same Date Range]
        |
        v
[3. Build Lookup Maps (by provider ID)]
        |
        v
[4. Compare Records]
        |
        +-- Match: count as matched
        +-- Mismatch: record discrepancy details
        +-- Missing Internal: record as "exists at provider only"
        +-- Missing Provider: record as "exists internally only"
        |
        v
[5. Generate Report]
        |
        v
[6. Store Report in Database]
        |
        v
[7. Log Audit Entry]
        |
        v
[8. Return Report ID / Summary]
```

## 3. Input

### Manual Trigger

```json
POST /api/v1/admin/reconciliation/run
{
  "date_range_start": "2026-06-01T00:00:00Z",
  "date_range_end": "2026-06-16T00:00:00Z"
}
```

### Scheduled Trigger

- Daily at 02:00 UTC (configurable).
- Reconciles the previous day by default.
- Configurable lookback window.

## 4. Step Details

### Step 1: Fetch Internal Records

Query the `payments` table for all records where `created_at` falls within the specified date range.

Fields needed: `id`, `external_id`, `amount`, `currency`, `status`.

Filter: only payments with `external_id IS NOT NULL` (payments that reached the provider).

### Step 2: Fetch Provider Records

Use the provider's `list_payment_intents` method to paginate through all payment intents created within the date range.

Handle pagination: continue fetching until no more results.

### Step 3: Build Lookup Maps

- Internal map: `{ external_id → internal_record }`
- Provider map: `{ provider_id → provider_record }`

### Step 4: Compare Records

For each internal record:
1. Look up the corresponding provider record by `external_id`.
2. If not found → discrepancy type: `missing_provider`.
3. If found, compare:
   - Amount matches? If not → `amount_mismatch`.
   - Currency matches? If not → `currency_mismatch`.
   - Status consistent? If not → `status_mismatch`.

For each provider record not in the internal map:
- Discrepancy type: `missing_internal`.

### Step 5: Generate Report

```python
@dataclass
class ReconciliationDiscrepancy:
    type: str  # missing_internal, missing_provider, amount_mismatch, status_mismatch, currency_mismatch
    internal_id: Optional[str]
    provider_id: Optional[str]
    field: Optional[str]  # which field mismatches
    internal_value: Optional[str]
    provider_value: Optional[str]
    details: str
```

### Step 6: Store Report

Insert into `reconciliation_reports` table:
- Date range
- Counts (total internal, total provider, matched, discrepancies)
- Discrepancy details as JSONB array
- Status: `completed` or `failed`
- Timestamps

### Step 7: Audit Log

Create audit entry:
- `action`: `reconciliation.completed`
- `actor_type`: `system` (for scheduled) or `admin` (for manual)
- `details`: summary of results
- `outcome`: `success` or `failure`

## 5. Status Consistency Rules

A status is considered consistent if the internal status maps to the expected provider status:

| Internal Status | Expected Stripe Statuses |
|----------------|-------------------------|
| pending | requires_payment_method, requires_confirmation |
| processing | processing, requires_capture |
| requires_action | requires_action |
| succeeded | succeeded |
| failed | (Stripe doesn't have a "failed" PI status; check last_payment_error) |
| canceled | canceled |
| refunded | succeeded (refunds are separate objects) |
| partially_refunded | succeeded (refunds are separate objects) |

For refunded/partially_refunded: also verify against Stripe's charges and refunds.

## 6. Performance Considerations

- **Pagination:** Stripe list API returns max 100 items per call. Use cursor-based pagination.
- **Rate limits:** Stripe has rate limits (~100 reads/sec in test mode, higher in production). Add delay between page fetches if needed.
- **Large date ranges:** For ranges with thousands of payments, process in batches (e.g., one day at a time).
- **Background execution:** Reconciliation should run as a background task to not block API requests. Return `202 Accepted` with a report ID immediately.

## 7. Alerting

Generate alerts for:
- Any `missing_internal` discrepancy (payment exists at Stripe but not locally — possible data loss).
- Any `missing_provider` discrepancy (payment exists locally but not at Stripe — possible orphan).
- `amount_mismatch` discrepancies (possible fraud or bug).
- Discrepancy rate exceeding threshold (e.g., > 1% of total records).

For v1, "alerting" means logging at ERROR level. Future versions can integrate with alerting systems (PagerDuty, Slack, etc.).

## 8. Manual Resolution

Reconciliation reports only flag discrepancies — they do not auto-correct. Resolution is manual:

1. Admin reviews the report via `GET /api/v1/admin/reconciliation/reports/{report_id}`.
2. For each discrepancy, admin investigates and takes corrective action.
3. Corrective actions are logged in the audit trail.

Auto-correction is intentionally excluded from v1 to prevent automated data corruption.
