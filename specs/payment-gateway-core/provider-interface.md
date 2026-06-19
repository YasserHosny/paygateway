# Payment Gateway Core Service — Provider Interface

## 1. Overview

The provider interface defines an abstract contract that all payment provider adapters must implement. This abstraction ensures that the core service business logic is decoupled from any specific provider, allowing new providers to be added by implementing this interface without changing the service layer.

## 2. Abstract Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class ProviderPaymentIntent:
    """Normalized payment intent response from any provider."""
    provider_id: str            # Provider-side ID (e.g., pi_xxx)
    status: str                 # Normalized status
    amount: int                 # Amount in smallest currency unit
    currency: str               # ISO 4217 currency code
    client_secret: Optional[str]  # Client secret for client-side confirmation
    provider_customer_id: Optional[str]
    failure_code: Optional[str]
    failure_message: Optional[str]
    metadata: dict
    created_at: datetime


@dataclass
class ProviderRefund:
    """Normalized refund response from any provider."""
    provider_id: str            # Provider-side refund ID
    payment_provider_id: str    # Provider-side payment ID this refund belongs to
    amount: int
    currency: str
    status: str                 # Normalized status
    failure_reason: Optional[str]
    created_at: datetime


@dataclass
class ProviderWebhookEvent:
    """Parsed and verified webhook event."""
    event_id: str               # Provider event ID
    event_type: str             # Event type string
    payload: dict               # Full event payload
    payment_provider_id: Optional[str]  # Associated payment intent ID if applicable
    refund_provider_id: Optional[str]   # Associated refund ID if applicable


class PaymentProvider(ABC):
    """Abstract payment provider interface.

    All payment provider adapters must implement this interface.
    Methods should raise ProviderError on failure.
    """

    @abstractmethod
    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ProviderPaymentIntent:
        """Create a payment intent with the provider."""
        ...

    @abstractmethod
    async def confirm_payment_intent(
        self,
        provider_payment_id: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> ProviderPaymentIntent:
        """Server-side confirm a payment intent."""
        ...

    @abstractmethod
    async def cancel_payment_intent(
        self,
        provider_payment_id: str,
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderPaymentIntent:
        """Cancel a payment intent."""
        ...

    @abstractmethod
    async def get_payment_intent(
        self,
        provider_payment_id: str,
    ) -> ProviderPaymentIntent:
        """Retrieve current state of a payment intent."""
        ...

    @abstractmethod
    async def create_refund(
        self,
        provider_payment_id: str,
        amount: Optional[int],
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderRefund:
        """Create a refund. If amount is None, refund the full amount."""
        ...

    @abstractmethod
    async def get_refund(
        self,
        provider_refund_id: str,
    ) -> ProviderRefund:
        """Retrieve current state of a refund."""
        ...

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        headers: dict,
    ) -> ProviderWebhookEvent:
        """Verify webhook signature and parse the event.

        Raises ProviderWebhookVerificationError if verification fails.
        """
        ...

    @abstractmethod
    async def list_payment_intents(
        self,
        created_after: datetime,
        created_before: datetime,
        limit: int = 100,
        starting_after: Optional[str] = None,
    ) -> tuple[list[ProviderPaymentIntent], Optional[str]]:
        """List payment intents for reconciliation.

        Returns (list_of_intents, next_cursor_or_none).
        """
        ...
```

## 3. Status Mapping

Each provider adapter must map provider-specific statuses to normalized statuses.

### Normalized Payment Statuses

| Status | Description |
|--------|-------------|
| pending | Created, awaiting confirmation |
| processing | Confirmation in progress |
| requires_action | Requires additional client action (e.g., 3DS) |
| succeeded | Payment completed successfully |
| failed | Payment failed |
| canceled | Payment canceled |

### Normalized Refund Statuses

| Status | Description |
|--------|-------------|
| pending | Refund initiated, not yet processed |
| succeeded | Refund completed |
| failed | Refund failed |

## 4. Error Handling

### Provider Error Hierarchy

```python
class ProviderError(Exception):
    """Base error for all provider errors."""
    def __init__(self, message: str, provider: str, code: Optional[str] = None):
        self.message = message
        self.provider = provider
        self.code = code
        super().__init__(message)


class ProviderConnectionError(ProviderError):
    """Provider is unreachable."""
    pass


class ProviderAuthenticationError(ProviderError):
    """Invalid provider credentials."""
    pass


class ProviderValidationError(ProviderError):
    """Provider rejected the request due to validation."""
    pass


class ProviderResourceNotFoundError(ProviderError):
    """Requested resource does not exist at the provider."""
    pass


class ProviderWebhookVerificationError(ProviderError):
    """Webhook signature verification failed."""
    pass


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""
    def __init__(self, message: str, provider: str, retry_after: Optional[int] = None):
        super().__init__(message, provider, code="RATE_LIMITED")
        self.retry_after = retry_after
```

## 5. Provider Factory

```python
def get_payment_provider(provider_name: str, config: Settings) -> PaymentProvider:
    """Factory function to instantiate the correct provider adapter.

    Args:
        provider_name: Name of the provider (e.g., "stripe").
        config: Application settings.

    Returns:
        An instance of PaymentProvider.

    Raises:
        ValueError: If the provider name is not supported.
    """
    providers = {
        "stripe": StripeProvider,
        # Future: "paypal": PayPalProvider,
        # Future: "adyen": AdyenProvider,
    }
    provider_class = providers.get(provider_name)
    if provider_class is None:
        raise ValueError(f"Unsupported payment provider: {provider_name}")
    return provider_class(config)
```

## 6. Adding a New Provider

To add a new payment provider:

1. Create a new file in `src/paygateway/providers/` (e.g., `paypal_provider.py`).
2. Implement the `PaymentProvider` abstract class.
3. Map provider-specific statuses to normalized statuses.
4. Map provider-specific errors to the `ProviderError` hierarchy.
5. Register the provider in the factory function.
6. Add provider-specific environment variables to config.
7. Write unit tests mocking the provider's SDK.
8. Write integration tests using the provider's test/sandbox mode.

No changes to the service layer, routes, or middleware should be required.

## 7. Design Decisions

1. **Async interface:** All methods are `async` to support non-blocking I/O with payment provider APIs.
2. **Dataclass DTOs:** `ProviderPaymentIntent` and `ProviderRefund` are simple dataclasses, not Pydantic models, to keep the provider interface lightweight and framework-independent.
3. **Idempotency key forwarding:** Provider methods accept idempotency keys so they can forward them to the provider's API (Stripe supports this natively).
4. **Reconciliation support:** The `list_payment_intents` method enables the reconciliation service to fetch provider-side records for comparison.
5. **Webhook verification in provider:** Each provider has its own signature verification logic, so it belongs in the adapter, not in the service layer.
