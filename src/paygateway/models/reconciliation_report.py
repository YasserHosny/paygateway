from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from paygateway.db.base import Base, UUIDPrimaryKeyMixin


class ReconciliationReport(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "reconciliation_reports"

    date_range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_internal: Mapped[int] = mapped_column(Integer, nullable=False)
    total_provider: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    discrepancies: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
