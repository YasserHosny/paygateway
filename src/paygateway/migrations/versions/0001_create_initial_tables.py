"""create_initial_tables

Revision ID: 0001
Revises:
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.VARCHAR(255), nullable=True),
        sa.Column("provider", sa.VARCHAR(50), nullable=False, server_default="stripe"),
        sa.Column("status", sa.VARCHAR(30), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.VARCHAR(3), nullable=False),
        sa.Column("customer_id", sa.VARCHAR(255), nullable=True),
        sa.Column("provider_customer_id", sa.VARCHAR(255), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.VARCHAR(255), nullable=False),
        sa.Column("client_secret", sa.VARCHAR(500), nullable=True),
        sa.Column("description", sa.VARCHAR(500), nullable=True),
        sa.Column("failure_code", sa.VARCHAR(100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_created_at", "payments", ["created_at"])
    op.create_index("ix_payments_external_id", "payments", ["external_id"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.VARCHAR(255), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.VARCHAR(255), nullable=True),
        sa.Column("status", sa.VARCHAR(30), nullable=False),
        sa.Column("idempotency_key", sa.VARCHAR(255), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], name="fk_refunds_payment_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_refunds_idempotency_key"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.VARCHAR(50), nullable=False),
        sa.Column("event_id", sa.VARCHAR(255), nullable=False),
        sa.Column("event_type", sa.VARCHAR(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_webhook_events_event_id"),
    )
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_processed", "webhook_events", ["processed"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.VARCHAR(255), nullable=False),
        sa.Column("request_path", sa.VARCHAR(500), nullable=False),
        sa.Column("request_method", sa.VARCHAR(10), nullable=False),
        sa.Column("request_hash", sa.VARCHAR(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_idempotency_records_key"),
    )
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.VARCHAR(255), nullable=False),
        sa.Column("actor_type", sa.VARCHAR(30), nullable=False),
        sa.Column("action", sa.VARCHAR(100), nullable=False),
        sa.Column("resource_type", sa.VARCHAR(50), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.VARCHAR(45), nullable=True),
        sa.Column("outcome", sa.VARCHAR(20), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_resource", "audit_log", ["resource_type", "resource_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(100), nullable=False),
        sa.Column("key_hash", sa.VARCHAR(128), nullable=False),
        sa.Column("key_prefix", sa.VARCHAR(8), nullable=False),
        sa.Column("role", sa.VARCHAR(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])

    op.create_table(
        "reconciliation_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("date_range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_internal", sa.Integer(), nullable=False),
        sa.Column("total_provider", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("discrepancy_count", sa.Integer(), nullable=False),
        sa.Column("discrepancies", sa.JSON(), nullable=True),
        sa.Column("status", sa.VARCHAR(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_reports")
    op.drop_table("api_keys")
    op.drop_table("audit_log")
    op.drop_table("idempotency_records")
    op.drop_table("webhook_events")
    op.drop_table("refunds")
    op.drop_table("payments")
