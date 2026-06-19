import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.db.session import get_db
from paygateway.dependencies import get_provider
from paygateway.middleware.authentication import AuthenticatedUser, require_role
from paygateway.providers.base import PaymentProvider
from paygateway.schemas.common import PaginatedResponse, PaginationInfo
from paygateway.schemas.payment import (
    CancelPaymentRequest,
    ConfirmPaymentRequest,
    CreatePaymentRequest,
    PaymentListFilters,
    PaymentResponse,
)
from paygateway.services import payment_service
from paygateway.services.payment_service import (
    PaymentNotCancelableError,
    PaymentNotFoundError,
    PaymentProviderError,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def _get_idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "IDEMPOTENCY_KEY_MISSING", "message": "Idempotency-Key header is required for POST requests", "details": {}}},
        )
    return key


def _payment_to_response(payment: object) -> PaymentResponse:
    p = payment  # type: ignore[assignment]
    return PaymentResponse(
        id=p.id,
        external_id=p.external_id,
        provider=p.provider,
        status=p.status,
        amount=p.amount,
        currency=p.currency,
        customer_id=p.customer_id,
        description=p.description,
        client_secret=p.client_secret,
        metadata=p.metadata_,
        created_at=p.created_at,
        updated_at=p.updated_at,
        confirmed_at=p.confirmed_at,
        canceled_at=p.canceled_at,
        failure_code=p.failure_code,
        failure_message=p.failure_message,
        refunded_amount=payment_service.compute_refunded_amount(p),
    )


@router.post("", status_code=201, response_model=PaymentResponse)
async def create_payment(
    body: CreatePaymentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
    user: AuthenticatedUser = Depends(require_role("admin", "service")),
) -> PaymentResponse:
    idempotency_key = _get_idempotency_key(request)
    ip = request.client.host if request.client else None
    try:
        payment = await payment_service.create_payment(
            db, provider, body, idempotency_key,
            actor_id=user.user_id, ip_address=ip,
        )
    except PaymentProviderError as e:
        raise HTTPException(status_code=502, detail={"error": {"code": "PROVIDER_ERROR", "message": e.message, "details": {}}}) from e
    return _payment_to_response(payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin", "service", "readonly")),
) -> PaymentResponse:
    try:
        payment = await payment_service.get_payment(db, payment_id)
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": str(e), "details": {}}}) from e
    resp = _payment_to_response(payment)
    resp.client_secret = None
    return resp


@router.get("", response_model=PaginatedResponse[PaymentResponse])
async def list_payments(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin", "readonly")),
    status: str | None = None,
    customer_id: str | None = None,
    currency: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[PaymentResponse]:
    from datetime import datetime

    filters = PaymentListFilters(
        status=status,
        customer_id=customer_id,
        currency=currency,
        created_after=datetime.fromisoformat(created_after) if created_after else None,
        created_before=datetime.fromisoformat(created_before) if created_before else None,
    )
    payments, total = await payment_service.list_payments(db, filters, limit, offset)
    data = []
    for p in payments:
        resp = _payment_to_response(p)
        resp.client_secret = None
        data.append(resp)
    return PaginatedResponse(
        data=data,
        pagination=PaginationInfo(
            total=total, limit=limit, offset=offset, has_more=(offset + limit < total),
        ),
    )


@router.post("/{payment_id}/confirm", response_model=PaymentResponse)
async def confirm_payment(
    payment_id: uuid.UUID,
    body: ConfirmPaymentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
    user: AuthenticatedUser = Depends(require_role("admin", "service")),
) -> PaymentResponse:
    idempotency_key = _get_idempotency_key(request)
    ip = request.client.host if request.client else None
    try:
        payment = await payment_service.confirm_payment(
            db, provider, payment_id, body.payment_method_id,
            idempotency_key, actor_id=user.user_id, ip_address=ip,
        )
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": str(e), "details": {}}}) from e
    except PaymentProviderError as e:
        raise HTTPException(status_code=502, detail={"error": {"code": "PROVIDER_ERROR", "message": e.message, "details": {}}}) from e
    return _payment_to_response(payment)


@router.post("/{payment_id}/cancel", response_model=PaymentResponse)
async def cancel_payment(
    payment_id: uuid.UUID,
    request: Request,
    body: CancelPaymentRequest | None = None,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
    user: AuthenticatedUser = Depends(require_role("admin", "service")),
) -> PaymentResponse:
    idempotency_key = _get_idempotency_key(request)
    ip = request.client.host if request.client else None
    reason = body.reason if body else None
    try:
        payment = await payment_service.cancel_payment(
            db, provider, payment_id, idempotency_key,
            reason=reason, actor_id=user.user_id, ip_address=ip,
        )
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": {"code": "PAYMENT_NOT_FOUND", "message": str(e), "details": {}}}) from e
    except PaymentNotCancelableError as e:
        raise HTTPException(status_code=409, detail={"error": {"code": "PAYMENT_NOT_CANCELABLE", "message": str(e), "details": {}}}) from e
    except PaymentProviderError as e:
        raise HTTPException(status_code=502, detail={"error": {"code": "PROVIDER_ERROR", "message": e.message, "details": {}}}) from e
    return _payment_to_response(payment)
