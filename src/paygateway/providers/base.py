from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ProviderPaymentIntent:
    provider_id: str
    status: str
    amount: int
    currency: str
    client_secret: Optional[str] = None
    provider_customer_id: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProviderRefund:
    provider_id: str
    payment_provider_id: str
    amount: int
    currency: str
    status: str
    failure_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProviderWebhookEvent:
    event_id: str
    event_type: str
    payload: dict
    payment_provider_id: Optional[str] = None
    refund_provider_id: Optional[str] = None


class ProviderError(Exception):
    def __init__(self, message: str, provider: str, code: Optional[str] = None):
        self.message = message
        self.provider = provider
        self.code = code
        super().__init__(message)


class ProviderConnectionError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderValidationError(ProviderError):
    pass


class ProviderResourceNotFoundError(ProviderError):
    pass


class ProviderWebhookVerificationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    def __init__(
        self, message: str, provider: str, retry_after: Optional[int] = None
    ):
        super().__init__(message, provider, code="RATE_LIMITED")
        self.retry_after = retry_after


class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ProviderPaymentIntent: ...

    @abstractmethod
    async def confirm_payment_intent(
        self,
        provider_payment_id: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> ProviderPaymentIntent: ...

    @abstractmethod
    async def cancel_payment_intent(
        self,
        provider_payment_id: str,
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderPaymentIntent: ...

    @abstractmethod
    async def get_payment_intent(
        self,
        provider_payment_id: str,
    ) -> ProviderPaymentIntent: ...

    @abstractmethod
    async def create_refund(
        self,
        provider_payment_id: str,
        amount: Optional[int],
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderRefund: ...

    @abstractmethod
    async def get_refund(
        self,
        provider_refund_id: str,
    ) -> ProviderRefund: ...

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        headers: dict,
    ) -> ProviderWebhookEvent: ...

    @abstractmethod
    async def list_payment_intents(
        self,
        created_after: datetime,
        created_before: datetime,
        limit: int = 100,
        starting_after: Optional[str] = None,
    ) -> tuple[list[ProviderPaymentIntent], Optional[str]]: ...
