from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.db.session import get_db
from paygateway.dependencies import get_provider
from paygateway.providers.base import PaymentProvider, ProviderWebhookVerificationError
from paygateway.schemas.webhook import WebhookResponse
from paygateway.services import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
) -> WebhookResponse:
    payload = await request.body()
    headers = dict(request.headers)

    try:
        await webhook_service.process_webhook(db, provider, payload, headers)
    except ProviderWebhookVerificationError as e:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_SIGNATURE", "message": e.message, "details": {}}}) from e

    return WebhookResponse()
