# Payment Gateway Core Service — Data Model

## 1. Overview

The data model uses PostgreSQL as the primary database. All tables use UUIDs as primary keys. Timestamps are stored in UTC. Monetary amounts are stored as integers in the smallest currency unit (e.g., cents for USD).

SQLAlchemy 2.x is used as the ORM. Alembic manages migrations.

## 2. Entity Relationship Diagram

```
+---------------+       +---------------+       +-------------------+
|   payments    |1----*|    refunds     |       |  webhook_events   |
+---------------+       +---------------+       +-------------------+
| id (PK)       |       | id (PK)       |       | id (PK)           |
| external_id   |       | payment_id(FK)|       | provider          |
| provider      |       | external_id   |       | event_id (UNIQUE) |
| status        |       | amount        |       | event_type        |
| amount        |       | reason        |       | payload (JSON)    |
| currency      |       | status        |       | processed         |
| customer_id   |       | idempotency_  |       | processed_at      |
| provider_     |       |   key         |       | created_at        |
|  customer_id  |       | created_at    |       +-------------------+
| metadata(JSON)|       | updated_at    |
| idempotency_  |       +---------------+
|   key         |
| client_secret |       +-------------------+   +-------------------+
| description   |       | idempotency_      |   |    audit_log      |
| created_at    |       |   records         |   +-------------------+
| updated_at    |       +-------------------+   | id (PK)           |
| confirmed_at  |       | id (PK)           |   | timestamp         |
| canceled_at   |       | key (UNIQUE)      |   | actor_id          |
| failure_code  |       | request_path      |   | actor_type        |
| failure_msg   |       | request_hash      |   | action            |
+---------------+       | response_status   |   | resource_type     |
                        | response_body     |   | resource_id       |
+---------------+       | expires_at        |   | details (JSON)    |
|   api_keys    |       | created_at        |   | ip_address        |
+---------------+       +-------------------+   | outcome           |
| id (PK)       |                               | created_at        |
| name          |                               +-------------------+
| key_hash      |
| key_prefix    |       +-------------------+
| role          |       | reconciliation_   |
| is_active     |       |   reports         |
| created_at    |       +-------------------+
| last_used_at  |       | id (PK)           |
| expires_at    |       | date_range_start  |
+---------------+       | date_range_end    |
                        | total_internal    |
                        | total_provider    |
                        | matched           |
                        | discrepancies(JSON|
                        | status            |
                        | created_at        |
                        | completed_at      |
                        +-------------------+
```

## 3. Table Definitions

### 3.1 `payments`

Primary table for tracking payment lifecycle.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Internal payment identifier |
| external_id | VARCHAR(255) | NULLABLE, INDEX | Provider-side ID (e.g., `pi_xxx` for Stripe) |
| provider | VARCHAR(50) | NOT NULL, default 'stripe' | Payment provider name |
| status | VARCHAR(30) | NOT NULL, INDEX | Payment status (enum enforced at app level) |
| amount | BIGINT | NOT NULL | Amount in smallest currency unit |
| currency | VARCHAR(3) | NOT NULL | ISO 4217 currency code (uppercase) |
| customer_id | VARCHAR(255) | NULLABLE, INDEX | Internal customer/user identifier |
| provider_customer_id | VARCHAR(255) | NULLABLE | Provider-side customer ID (e.g., `cus_xxx`) |
| metadata | JSONB | NULLABLE, default {} | Arbitrary key-value metadata from client |
| idempotency_key | VARCHAR(255) | UNIQUE, NOT NULL | Client-provided idempotency key |
| client_secret | VARCHAR(500) | NULLABLE | Provider client secret for client-side confirmation |
| description | VARCHAR(500) | NULLABLE | Human-readable description |
| failure_code | VARCHAR(100) | NULLABLE | Provider failure code if payment failed |
| failure_message | TEXT | NULLABLE | Provider failure message |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | Creation time (UTC) |
| updated_at | TIMESTAMP(tz) | NOT NULL, default now() | Last modification time (UTC) |
| confirmed_at | TIMESTAMP(tz) | NULLABLE | When payment was confirmed |
| canceled_at | TIMESTAMP(tz) | NULLABLE | When payment was canceled |

**Indexes:**
- `ix_payments_status` on `status`
- `ix_payments_customer_id` on `customer_id`
- `ix_payments_created_at` on `created_at`
- `ix_payments_external_id` on `external_id`
- `uq_payments_idempotency_key` UNIQUE on `idempotency_key`

**Status Enum Values:**
`pending`, `processing`, `requires_action`, `succeeded`, `failed`, `canceled`, `refunded`, `partially_refunded`, `disputed`

### 3.2 `refunds`

Tracks refund requests and their lifecycle.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Internal refund identifier |
| payment_id | UUID | FK(payments.id), NOT NULL, INDEX | Associated payment |
| external_id | VARCHAR(255) | NULLABLE | Provider-side refund ID (e.g., `re_xxx`) |
| amount | BIGINT | NOT NULL | Refund amount in smallest currency unit |
| reason | VARCHAR(255) | NULLABLE | Reason for refund |
| status | VARCHAR(30) | NOT NULL | Refund status |
| idempotency_key | VARCHAR(255) | UNIQUE, NOT NULL | Idempotency key |
| failure_reason | TEXT | NULLABLE | Reason if refund failed |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | Creation time |
| updated_at | TIMESTAMP(tz) | NOT NULL, default now() | Last update time |

**Indexes:**
- `ix_refunds_payment_id` on `payment_id`
- `uq_refunds_idempotency_key` UNIQUE on `idempotency_key`

**Status Enum Values:**
`pending`, `succeeded`, `failed`

### 3.3 `webhook_events`

Stores received webhook events for idempotent processing.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Internal record ID |
| provider | VARCHAR(50) | NOT NULL | Provider name |
| event_id | VARCHAR(255) | UNIQUE, NOT NULL | Provider event ID for deduplication |
| event_type | VARCHAR(100) | NOT NULL, INDEX | Event type string |
| payload | JSONB | NOT NULL | Raw event payload |
| processed | BOOLEAN | NOT NULL, default false | Processing completion flag |
| processing_error | TEXT | NULLABLE | Error message if processing failed |
| processed_at | TIMESTAMP(tz) | NULLABLE | When processing completed |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | When event was received |

**Indexes:**
- `uq_webhook_events_event_id` UNIQUE on `event_id`
- `ix_webhook_events_event_type` on `event_type`
- `ix_webhook_events_processed` on `processed`

### 3.4 `idempotency_records`

Caches responses for idempotent request handling.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Record ID |
| key | VARCHAR(255) | UNIQUE, NOT NULL | Idempotency key |
| request_path | VARCHAR(500) | NOT NULL | Request endpoint path |
| request_method | VARCHAR(10) | NOT NULL | HTTP method |
| request_hash | VARCHAR(64) | NOT NULL | SHA-256 hash of request body |
| response_status | INTEGER | NOT NULL | Cached HTTP response status |
| response_body | JSONB | NOT NULL | Cached response body |
| expires_at | TIMESTAMP(tz) | NOT NULL, INDEX | When this record expires |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | Creation time |

**Indexes:**
- `uq_idempotency_records_key` UNIQUE on `key`
- `ix_idempotency_records_expires_at` on `expires_at`

### 3.5 `audit_log`

Append-only audit trail. No UPDATE or DELETE operations permitted.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Record ID |
| timestamp | TIMESTAMP(tz) | NOT NULL, INDEX | When the action occurred |
| actor_id | VARCHAR(255) | NOT NULL | Who performed the action |
| actor_type | VARCHAR(30) | NOT NULL | Actor type: user, system, webhook, admin |
| action | VARCHAR(100) | NOT NULL, INDEX | Action name (e.g., payment.created) |
| resource_type | VARCHAR(50) | NOT NULL | Resource type (payment, refund, etc.) |
| resource_id | UUID | NULLABLE | ID of affected resource |
| details | JSONB | NULLABLE | Additional context |
| ip_address | VARCHAR(45) | NULLABLE | Source IP (supports IPv6) |
| outcome | VARCHAR(20) | NOT NULL | success or failure |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | Record insertion time |

**Indexes:**
- `ix_audit_log_timestamp` on `timestamp`
- `ix_audit_log_action` on `action`
- `ix_audit_log_resource` on `(resource_type, resource_id)`

### 3.6 `api_keys`

API key management for service authentication.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Key ID |
| name | VARCHAR(100) | NOT NULL | Human-readable name |
| key_hash | VARCHAR(128) | UNIQUE, NOT NULL | SHA-256 hash of the full API key |
| key_prefix | VARCHAR(8) | NOT NULL | First 8 characters for identification |
| role | VARCHAR(20) | NOT NULL | Role: admin, service, readonly |
| is_active | BOOLEAN | NOT NULL, default true | Whether the key is active |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | Creation time |
| last_used_at | TIMESTAMP(tz) | NULLABLE | Last usage time |
| expires_at | TIMESTAMP(tz) | NULLABLE | Optional expiry |

**Indexes:**
- `uq_api_keys_key_hash` UNIQUE on `key_hash`
- `ix_api_keys_key_prefix` on `key_prefix`

### 3.7 `reconciliation_reports`

Stores reconciliation run results.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Report ID |
| date_range_start | TIMESTAMP(tz) | NOT NULL | Start of reconciled date range |
| date_range_end | TIMESTAMP(tz) | NOT NULL | End of reconciled date range |
| total_internal | INTEGER | NOT NULL | Number of internal records checked |
| total_provider | INTEGER | NOT NULL | Number of provider records checked |
| matched_count | INTEGER | NOT NULL | Number of matching records |
| discrepancy_count | INTEGER | NOT NULL | Number of discrepancies found |
| discrepancies | JSONB | NULLABLE | Array of discrepancy details |
| status | VARCHAR(30) | NOT NULL | completed, failed, in_progress |
| created_at | TIMESTAMP(tz) | NOT NULL, default now() | When the run started |
| completed_at | TIMESTAMP(tz) | NULLABLE | When the run finished |

## 4. Migration Strategy

- Use Alembic for all schema changes.
- Initial migration creates all tables.
- Each subsequent change gets its own migration file with descriptive name.
- Migrations must be reversible (include downgrade).
- Run migrations as part of deployment pipeline before starting the application.

## 5. Data Retention

- **Payments and refunds:** Retained indefinitely (financial records).
- **Webhook events:** Retained for 90 days, then archivable.
- **Idempotency records:** Expired records cleaned up daily via background job.
- **Audit log:** Retained indefinitely (compliance).
- **Reconciliation reports:** Retained for 1 year, then archivable.
