import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.db.session import get_db
from paygateway.dependencies import get_provider
from paygateway.middleware.authentication import AuthenticatedUser, require_role
from paygateway.providers.base import PaymentProvider
from paygateway.schemas.common import PaginatedResponse, PaginationInfo
from paygateway.schemas.refund import CreateRefundRequest, RefundResponse
from paygateway.services import refund_service
from paygateway.services.payment_service import PaymentNotFoundError, PaymentProviderError
from paygateway.services.refund_service import (
    PaymentNotRefundableError,
    RefundExceedsAmountError,
    RefundNotFoundError,
)

router = APIRouter(tags=["refunds"])


def _get_idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "IDEMPOTENCY_KEY_MISSING", "message": "Idempotency-Key header is required", "details": {}}},
        )
    return key


@router.post("/payments/{payment_id}/refund", status_code=201, response_model=RefundResponse)
async def create_refund(
    payment_id: uuid.UUID,
    request: Request,
    body: CreateRefundRequest | None = None,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> RefundResponse:
    idempotency_key = _get_idempotency_key(request)
    ip = request.client.host if request.client else None
    amount = body.amount if body else None
    reason = body.reason if body else None
    try:
        refund = await refund_service.create_refund(
            db, provider, payment_id, idempotency_key,
            amount=amount, reason=reason,
            actor_id=user.user_id, ip_address=ip,
        )
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": str(e), "details": {}}}) from e
    except PaymentNotRefundableError as e:
        raise HTTPException(status_code=409, detail={"error": {"code": "PAYMENT_NOT_REFUNDABLE", "message": str(e), "details": {}}}) from e
    except RefundExceedsAmountError as e:
        raise HTTPException(status_code=409, detail={"error": {"code": "REFUND_EXCEEDS_AMOUNT", "message": str(e), "details": {}}}) from e
    except PaymentProviderError as e:
        raise HTTPException(status_code=502, detail={"error": {"code": "PROVIDER_ERROR", "message": e.message, "details": {}}}) from e
    return RefundResponse.model_validate(refund)


@router.get("/payments/{payment_id}/refunds", response_model=PaginatedResponse[RefundResponse])
async def list_refunds(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin", "readonly")),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[RefundResponse]:
    try:
        refunds, total = await refund_service.list_refunds_for_payment(db, payment_id, limit, offset)
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": str(e), "details": {}}}) from e
    return PaginatedResponse(
        data=[RefundResponse.model_validate(r) for r in refunds],
        pagination=PaginationInfo(
            total=total, limit=limit, offset=offset, has_more=(offset + limit < total),
        ),
    )


@router.get("/refunds/{refund_id}", response_model=RefundResponse)
async def get_refund(
    refund_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin", "readonly")),
) -> RefundResponse:
    try:
        refund = await refund_service.get_refund(db, refund_id)
    except RefundNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "REFUND_NOT_FOUND", "message": str(e), "details": {}}}) from e
    return RefundResponse.model_validate(refund)
