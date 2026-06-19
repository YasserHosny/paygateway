import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateRefundRequest(BaseModel):
    amount: int | None = Field(default=None, gt=0, le=99999999)
    reason: str | None = Field(default=None, max_length=255)


class RefundResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    external_id: str | None = None
    amount: int
    reason: str | None = None
    status: str
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
