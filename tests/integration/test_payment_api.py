import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_create_payment_success(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 5000
    assert data["currency"] == "USD"
    assert data["status"] == "pending"
    assert data["client_secret"] is not None
    assert "id" in data


@pytest.mark.integration
async def test_create_payment_missing_idempotency_key(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_create_payment_invalid_amount(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payments",
        json={"amount": -1, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_get_payment_success(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 3000, "currency": "eur"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/payments/{payment_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == payment_id
    assert resp.json()["client_secret"] is None


@pytest.mark.integration
async def test_get_payment_not_found(client: AsyncClient):
    resp = await client.get(f"/api/v1/payments/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_list_payments(client: AsyncClient):
    for i in range(3):
        await client.post(
            "/api/v1/payments",
            json={"amount": 1000 * (i + 1), "currency": "usd"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 3
    assert data["pagination"]["total"] == 3


@pytest.mark.integration
async def test_unauthenticated_request(client: AsyncClient):
    client.headers.pop("X-API-Key", None)
    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_confirm_payment_success(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/confirm",
        json={"payment_method_id": "pm_card_visa"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"


@pytest.mark.integration
async def test_confirm_payment_not_found(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/confirm",
        json={"payment_method_id": "pm_card_visa"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "PAYMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_cancel_payment_success(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"amount": 5000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    payment_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/cancel",
        json={"reason": "requested_by_customer"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "canceled"


@pytest.mark.integration
async def test_cancel_payment_not_found(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/payments/{uuid.uuid4()}/cancel",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# list filters & pagination
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_payments_filter_by_status(client: AsyncClient):
    await client.post(
        "/api/v1/payments",
        json={"amount": 1000, "currency": "usd"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    resp = await client.get("/api/v1/payments?status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] >= 1
    assert all(p["status"] == "pending" for p in data["data"])


@pytest.mark.integration
async def test_list_payments_filter_by_currency(client: AsyncClient):
    await client.post(
        "/api/v1/payments",
        json={"amount": 2000, "currency": "eur"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    resp = await client.get("/api/v1/payments?currency=eur")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pagination"]["total"] >= 1
    assert all(p["currency"] == "EUR" for p in data["data"])


@pytest.mark.integration
async def test_list_payments_pagination(client: AsyncClient):
    for _ in range(5):
        await client.post(
            "/api/v1/payments",
            json={"amount": 500, "currency": "usd"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    page1 = await client.get("/api/v1/payments?limit=2&offset=0")
    page2 = await client.get("/api/v1/payments?limit=2&offset=2")

    assert page1.status_code == 200
    assert page2.status_code == 200
    assert len(page1.json()["data"]) == 2
    assert len(page2.json()["data"]) == 2
    assert page1.json()["pagination"]["total"] == 5
    assert page1.json()["pagination"]["has_more"] is True
    # Pages must contain different records
    ids1 = {p["id"] for p in page1.json()["data"]}
    ids2 = {p["id"] for p in page2.json()["data"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.integration
async def test_list_payments_invalid_limit(client: AsyncClient):
    resp = await client.get("/api/v1/payments?limit=0")
    assert resp.status_code == 422


@pytest.mark.integration
async def test_list_payments_limit_exceeds_max(client: AsyncClient):
    resp = await client.get("/api/v1/payments?limit=101")
    assert resp.status_code == 422
