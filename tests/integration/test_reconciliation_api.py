import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from paygateway.providers.base import ProviderPaymentIntent


def _make_pi(provider_id: str) -> ProviderPaymentIntent:
    return ProviderPaymentIntent(
        provider_id=provider_id, status="succeeded", amount=5000, currency="USD"
    )


@pytest.mark.integration
async def test_run_reconciliation_success(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.list_payment_intents.return_value = ([], None)
    resp = await client.post(
        "/api/v1/admin/reconciliation/run",
        json={
            "date_range_start": "2024-01-01T00:00:00Z",
            "date_range_end": "2024-01-02T00:00:00Z",
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "report_id" in data
    assert data["status"] == "completed"


@pytest.mark.integration
async def test_run_reconciliation_invalid_date_range(client: AsyncClient):
    resp = await client.post(
        "/api/v1/admin/reconciliation/run",
        json={
            "date_range_start": "2024-01-02T00:00:00Z",
            "date_range_end": "2024-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_list_reconciliation_reports_empty(client: AsyncClient):
    resp = await client.get("/api/v1/admin/reconciliation/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] == 0
    assert data["data"] == []


@pytest.mark.integration
async def test_get_reconciliation_report_not_found(client: AsyncClient):
    resp = await client.get(f"/api/v1/admin/reconciliation/reports/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_list_reports_after_run(client: AsyncClient, mock_provider: AsyncMock):
    mock_provider.list_payment_intents.return_value = ([], None)
    run_resp = await client.post(
        "/api/v1/admin/reconciliation/run",
        json={
            "date_range_start": "2024-01-01T00:00:00Z",
            "date_range_end": "2024-01-02T00:00:00Z",
        },
    )
    report_id = run_resp.json()["report_id"]

    list_resp = await client.get("/api/v1/admin/reconciliation/reports")
    assert list_resp.status_code == 200
    assert list_resp.json()["pagination"]["total"] == 1

    get_resp = await client.get(f"/api/v1/admin/reconciliation/reports/{report_id}")
    assert get_resp.status_code == 200
    assert str(get_resp.json()["id"]) == report_id


@pytest.mark.integration
async def test_reconciliation_requires_admin(client: AsyncClient):
    client.headers.pop("X-API-Key", None)
    resp = await client.post(
        "/api/v1/admin/reconciliation/run",
        json={
            "date_range_start": "2024-01-01T00:00:00Z",
            "date_range_end": "2024-01-02T00:00:00Z",
        },
    )
    assert resp.status_code == 401
