import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.db.session import get_db
from paygateway.dependencies import get_provider
from paygateway.middleware.authentication import AuthenticatedUser, require_role
from paygateway.providers.base import PaymentProvider
from paygateway.schemas.common import PaginatedResponse, PaginationInfo
from paygateway.schemas.reconciliation import (
    ReconciliationReportResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
)
from paygateway.services import reconciliation_service

router = APIRouter(prefix="/admin/reconciliation", tags=["reconciliation"])


@router.post("/run", status_code=202, response_model=ReconciliationRunResponse)
async def run_reconciliation(
    body: ReconciliationRunRequest,
    db: AsyncSession = Depends(get_db),
    provider: PaymentProvider = Depends(get_provider),
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> ReconciliationRunResponse:
    report = await reconciliation_service.run_reconciliation(
        db, provider,
        date_range_start=body.date_range_start,
        date_range_end=body.date_range_end,
        actor_id=user.user_id,
    )
    return ReconciliationRunResponse(
        report_id=report.id,
        status=report.status,
    )


@router.get("/reports", response_model=PaginatedResponse[ReconciliationReportResponse])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin")),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[ReconciliationReportResponse]:
    reports, total = await reconciliation_service.list_reports(db, limit, offset)
    return PaginatedResponse(
        data=[ReconciliationReportResponse.model_validate(r) for r in reports],
        pagination=PaginationInfo(
            total=total, limit=limit, offset=offset, has_more=(offset + limit < total),
        ),
    )


@router.get("/reports/{report_id}", response_model=ReconciliationReportResponse)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> ReconciliationReportResponse:
    report = await reconciliation_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "REPORT_NOT_FOUND", "message": "Report not found", "details": {}}})
    return ReconciliationReportResponse.model_validate(report)
