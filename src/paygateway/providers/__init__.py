from paygateway.config import Settings
from paygateway.providers.base import PaymentProvider
from paygateway.providers.stripe_provider import StripeProvider


def get_payment_provider(provider_name: str = "stripe", config: Settings | None = None) -> PaymentProvider:
    if config is None:
        from paygateway.config import get_settings
        config = get_settings()

    providers: dict[str, type[PaymentProvider]] = {
        "stripe": StripeProvider,
    }
    provider_class = providers.get(provider_name)
    if provider_class is None:
        msg = f"Unsupported payment provider: {provider_name}"
        raise ValueError(msg)
    return provider_class(config)
