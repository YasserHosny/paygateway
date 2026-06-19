import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreatePaymentRequest(BaseModel):
    amount: int = Field(..., gt=0, le=99999999)
    currency: str = Field(..., min_length=3, max_length=3)
    customer_id: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    metadata: dict[str, str] | None = Field(default=None)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        if len(v) > 20:
            msg = "Metadata must have at most 20 keys"
            raise ValueError(msg)
        for key, val in v.items():
            if len(key) > 40:
                msg = f"Metadata key '{key}' exceeds 40 characters"
                raise ValueError(msg)
            if len(val) > 500:
                msg = f"Metadata value for key '{key}' exceeds 500 characters"
                raise ValueError(msg)
        return v


class PaymentResponse(BaseModel):
    id: uuid.UUID
    external_id: str | None = None
    provider: str
    status: str
    amount: int
    currency: str
    customer_id: str | None = None
    description: str | None = None
    client_secret: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    canceled_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    refunded_amount: int = 0

    model_config = {"from_attributes": True}


class PaymentListFilters(BaseModel):
    status: str | None = None
    customer_id: str | None = None
    currency: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class ConfirmPaymentRequest(BaseModel):
    payment_method_id: str = Field(..., min_length=1)


class CancelPaymentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
