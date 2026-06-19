from fastapi import APIRouter

from paygateway.routes.payments import router as payments_router
from paygateway.routes.reconciliation import router as reconciliation_router
from paygateway.routes.refunds import router as refunds_router
from paygateway.routes.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(payments_router)
api_v1_router.include_router(refunds_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(reconciliation_router)
