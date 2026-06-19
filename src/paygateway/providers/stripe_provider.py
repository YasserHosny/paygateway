import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import stripe

from paygateway.config import Settings
from paygateway.providers.base import (
    PaymentProvider,
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderPaymentIntent,
    ProviderRateLimitError,
    ProviderRefund,
    ProviderResourceNotFoundError,
    ProviderValidationError,
    ProviderWebhookEvent,
    ProviderWebhookVerificationError,
)

STRIPE_PAYMENT_STATUS_MAP = {
    "requires_payment_method": "pending",
    "requires_confirmation": "pending",
    "requires_action": "requires_action",
    "processing": "processing",
    "requires_capture": "processing",
    "succeeded": "succeeded",
    "canceled": "canceled",
}

STRIPE_REFUND_STATUS_MAP = {
    "pending": "pending",
    "succeeded": "succeeded",
    "failed": "failed",
    "canceled": "failed",
}


def _map_stripe_error(e: Exception) -> ProviderError:
    if isinstance(e, stripe.AuthenticationError):
        return ProviderAuthenticationError(str(e), "stripe")
    if isinstance(e, stripe.PermissionError):
        return ProviderAuthenticationError(str(e), "stripe")
    if isinstance(e, stripe.InvalidRequestError):
        return ProviderValidationError(str(e), "stripe", code=getattr(e, "code", None))
    if isinstance(e, stripe.APIConnectionError):
        return ProviderConnectionError(str(e), "stripe")
    if isinstance(e, stripe.RateLimitError):
        return ProviderRateLimitError(str(e), "stripe")
    return ProviderError(str(e), "stripe")


class StripeProvider(PaymentProvider):
    def __init__(self, config: Settings) -> None:
        self._api_key = config.STRIPE_SECRET_KEY
        self._webhook_secret = config.STRIPE_WEBHOOK_SECRET
        self._api_version = config.STRIPE_API_VERSION
        stripe.api_key = self._api_key
        stripe.api_version = self._api_version

    def _map_payment_intent(self, pi: Any) -> ProviderPaymentIntent:
        return ProviderPaymentIntent(
            provider_id=pi.id,
            status=STRIPE_PAYMENT_STATUS_MAP.get(pi.status, pi.status),
            amount=pi.amount,
            currency=pi.currency.upper(),
            client_secret=pi.client_secret,
            provider_customer_id=getattr(pi, "customer", None),
            failure_code=(
                pi.last_payment_error.code if pi.last_payment_error else None
            ),
            failure_message=(
                pi.last_payment_error.message if pi.last_payment_error else None
            ),
            metadata=pi.metadata._data.copy() if pi.metadata else {},
            created_at=datetime.fromtimestamp(pi.created, tz=timezone.utc),
        )

    def _map_refund(self, refund: Any) -> ProviderRefund:
        return ProviderRefund(
            provider_id=refund.id,
            payment_provider_id=refund.payment_intent or "",
            amount=refund.amount,
            currency=refund.currency.upper(),
            status=STRIPE_REFUND_STATUS_MAP.get(refund.status, refund.status),
            failure_reason=getattr(refund, "failure_reason", None),
            created_at=datetime.fromtimestamp(refund.created, tz=timezone.utc),
        )

    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        idempotency_key: str,
        customer_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ProviderPaymentIntent:
        params: dict[str, Any] = {
            "amount": amount,
            "currency": currency.lower(),
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        }
        if customer_id:
            params["customer"] = customer_id
        if description:
            params["description"] = description
        if metadata:
            params["metadata"] = metadata

        try:
            pi = await asyncio.to_thread(
                stripe.PaymentIntent.create,
                idempotency_key=f"stripe_{idempotency_key}",
                **params,
            )
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_payment_intent(pi)

    async def confirm_payment_intent(
        self,
        provider_payment_id: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> ProviderPaymentIntent:
        try:
            pi = await asyncio.to_thread(
                stripe.PaymentIntent.confirm,
                provider_payment_id,
                payment_method=payment_method_id,
                idempotency_key=f"stripe_{idempotency_key}",
            )
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_payment_intent(pi)

    async def cancel_payment_intent(
        self,
        provider_payment_id: str,
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderPaymentIntent:
        params: dict[str, Any] = {}
        if reason:
            cancellation_reasons = {
                "duplicate", "fraudulent", "requested_by_customer", "abandoned"
            }
            params["cancellation_reason"] = (
                reason if reason in cancellation_reasons else "requested_by_customer"
            )
        try:
            pi = await asyncio.to_thread(
                stripe.PaymentIntent.cancel,
                provider_payment_id,
                idempotency_key=f"stripe_{idempotency_key}",
                **params,
            )
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_payment_intent(pi)

    async def get_payment_intent(
        self,
        provider_payment_id: str,
    ) -> ProviderPaymentIntent:
        try:
            pi = await asyncio.to_thread(
                stripe.PaymentIntent.retrieve, provider_payment_id
            )
        except stripe.InvalidRequestError as e:
            raise ProviderResourceNotFoundError(str(e), "stripe") from e
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_payment_intent(pi)

    async def create_refund(
        self,
        provider_payment_id: str,
        amount: Optional[int],
        idempotency_key: str,
        reason: Optional[str] = None,
    ) -> ProviderRefund:
        params: dict[str, Any] = {"payment_intent": provider_payment_id}
        if amount is not None:
            params["amount"] = amount
        if reason:
            stripe_reasons = {"duplicate", "fraudulent", "requested_by_customer"}
            params["reason"] = (
                reason if reason in stripe_reasons else "requested_by_customer"
            )
        try:
            refund = await asyncio.to_thread(
                stripe.Refund.create,
                idempotency_key=f"stripe_{idempotency_key}",
                **params,
            )
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_refund(refund)

    async def get_refund(
        self,
        provider_refund_id: str,
    ) -> ProviderRefund:
        try:
            refund = await asyncio.to_thread(
                stripe.Refund.retrieve, provider_refund_id
            )
        except stripe.InvalidRequestError as e:
            raise ProviderResourceNotFoundError(str(e), "stripe") from e
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e
        return self._map_refund(refund)

    async def verify_webhook(
        self,
        payload: bytes,
        headers: dict,
    ) -> ProviderWebhookEvent:
        sig_header = headers.get("stripe-signature", "")
        if not sig_header:
            raise ProviderWebhookVerificationError(
                "Missing Stripe-Signature header", "stripe"
            )
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=self._webhook_secret,
            )
        except stripe.SignatureVerificationError as e:
            raise ProviderWebhookVerificationError(str(e), "stripe") from e

        payment_provider_id = None
        refund_provider_id = None
        data_object = event["data"]["object"]

        if event["type"].startswith("payment_intent"):
            payment_provider_id = data_object.get("id")
        elif event["type"].startswith("charge.refund"):
            refund_provider_id = data_object.get("id")
            payment_provider_id = data_object.get("payment_intent")
        elif event["type"].startswith("charge"):
            payment_provider_id = data_object.get("payment_intent")

        return ProviderWebhookEvent(
            event_id=event["id"],
            event_type=event["type"],
            payload=dict(event),
            payment_provider_id=payment_provider_id,
            refund_provider_id=refund_provider_id,
        )

    async def list_payment_intents(
        self,
        created_after: datetime,
        created_before: datetime,
        limit: int = 100,
        starting_after: Optional[str] = None,
    ) -> tuple[list[ProviderPaymentIntent], Optional[str]]:
        params: dict[str, Any] = {
            "created": {
                "gte": int(created_after.timestamp()),
                "lt": int(created_before.timestamp()),
            },
            "limit": limit,
        }
        if starting_after:
            params["starting_after"] = starting_after

        try:
            result = await asyncio.to_thread(
                stripe.PaymentIntent.list, **params
            )
        except stripe.StripeError as e:
            raise _map_stripe_error(e) from e

        intents = [self._map_payment_intent(pi) for pi in result.data]
        next_cursor = result.data[-1].id if result.has_more and result.data else None
        return intents, next_cursor
