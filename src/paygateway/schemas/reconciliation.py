import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReconciliationRunRequest(BaseModel):
    date_range_start: datetime
    date_range_end: datetime

    def model_post_init(self, __context: object) -> None:
        if self.date_range_start >= self.date_range_end:
            msg = "date_range_start must be before date_range_end"
            raise ValueError(msg)


class ReconciliationDiscrepancy(BaseModel):
    type: str
    internal_id: str | None = None
    provider_id: str | None = None
    field: str | None = None
    internal_value: str | None = None
    provider_value: str | None = None
    details: str


class ReconciliationReportResponse(BaseModel):
    id: uuid.UUID
    date_range_start: datetime
    date_range_end: datetime
    total_internal: int
    total_provider: int
    matched_count: int
    discrepancy_count: int
    discrepancies: list[ReconciliationDiscrepancy] | None = None
    status: str
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReconciliationRunResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    message: str = Field(default="Reconciliation started.")
