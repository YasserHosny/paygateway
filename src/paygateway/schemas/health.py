from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str]
    timestamp: datetime


class InfoResponse(BaseModel):
    service: str = "payment-gateway-core"
    version: str = "1.0.0"
    environment: str
