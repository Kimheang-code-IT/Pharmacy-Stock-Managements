"""Supplier debt payments: overpayment rejection, history, permissions (spec 2.1.5)."""

from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login

VIEWER_EMAIL = "sup-debt-viewer@example.com"
VIEWER_PASSWORD = "viewerpass1"


@pytest.fixture
async def viewer_only_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=VIEWER_EMAIL,
        password=VIEWER_PASSWORD,
        role_name="Supplier Debt Viewer",
        permissions=["supplier.view"],
    )
    await db_session.commit()
    data = await login(client, VIEWER_EMAIL, VIEWER_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _supplier_with_debt(client, headers, *, code: str, total="20.00", paid="5.00") -> tuple[dict, dict]:
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": code, "name": f"Supplier {code}", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"CS-{code}", "name": f"Cat {code}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"SUP-{code}",
                "name": f"Widget {code}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
            },
            headers=headers,
        )
    ).json()["data"]

    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": paid,
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text

    debts = await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)
    assert debts.status_code == 200, debts.text
    debt_rows = debts.json()["data"]
    assert len(debt_rows) == 1
    return supplier, debt_rows[0]


@pytest.mark.asyncio
async def test_stock_in_unpaid_portion_becomes_supplier_debt(client):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-1")
    assert Decimal(debt["original_amount"]) == Decimal("20.00")
    assert Decimal(debt["paid_amount"]) == Decimal("5.00")
    assert Decimal(debt["remaining_amount"]) == Decimal("15.00")
    assert debt["status"] == "PARTIAL"
    assert debt["document_no"].startswith("STI-")


@pytest.mark.asyncio
async def test_partial_then_full_supplier_payment(client):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-2")

    first = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "10.00", "payment_method": "BANK_QR", "reference_no": "TR-1"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    payment = first.json()["data"]
    assert payment["payment_no"].startswith("SDP-")
    assert payment["payment_type"] == "SUPPLIER_DEBT_PAYMENT"
    assert payment["supplier_debt_id"] == debt["id"]

    second = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert second.status_code == 201, second.text

    debts = await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)
    row = debts.json()["data"][0]
    assert row["status"] == "PAID"
    assert Decimal(row["remaining_amount"]) == Decimal("0.00")
    assert Decimal(row["paid_amount"]) == Decimal("20.00")


@pytest.mark.asyncio
async def test_supplier_payment_rejects_overpayment(client):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-3")

    response = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "16.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "amount" in response.json()["detail"].get("field_errors", {})


@pytest.mark.asyncio
async def test_supplier_payment_history_lists_payments(client):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-4", paid="2.00")

    await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "8.00", "payment_method": "CASH"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "10.00", "payment_method": "BANK_QR"},
        headers=headers,
    )

    history = await client.get(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments", headers=headers
    )
    assert history.status_code == 200, history.text
    rows = history.json()["data"]
    assert len(rows) == 2
    assert Decimal(sum(Decimal(r["amount"]) for r in rows)) == Decimal("18.00")
    assert all(r["payment_type"] == "SUPPLIER_DEBT_PAYMENT" for r in rows)


@pytest.mark.asyncio
async def test_supplier_payment_requires_permission(client, viewer_only_headers):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-5")

    denied = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=viewer_only_headers,
    )
    assert denied.status_code == 403

    history = await client.get(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments", headers=viewer_only_headers
    )
    assert history.status_code == 200


@pytest.mark.asyncio
async def test_supplier_payment_scoped_to_owning_supplier(client):
    headers = await admin_headers(client)
    supplier, debt = await _supplier_with_debt(client, headers, code="SDP-6")
    other = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": "SDP-OTHER", "name": "Other Supplier", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]

    response = await client.post(
        f"/api/v1/suppliers/{other['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 404
