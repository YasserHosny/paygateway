from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.config import get_settings
from paygateway.db.session import get_db
from paygateway.middleware.authentication import AuthenticatedUser, get_current_user, require_role
from paygateway.providers import get_payment_provider
from paygateway.providers.base import PaymentProvider


def get_provider() -> PaymentProvider:
    return get_payment_provider("stripe", get_settings())


RequireAdmin = Depends(require_role("admin"))
RequireService = Depends(require_role("admin", "service"))
RequireReadonly = Depends(require_role("admin", "service", "readonly"))
