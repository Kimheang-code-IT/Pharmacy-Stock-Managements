"""Flat party-level payment endpoints (frontend fallback when no debt row is
selected): settle open debts oldest-first in one transaction, reject
overpayment, immutable payment rows, server-side permissions."""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login


async def _two_customer_debts(client, headers, tag: str):
    """Customer with two open debts: 20.00 then 10.00 (oldest first)."""
    product = await make_stocked_product(client, headers, sku=f"CPAY-{tag}", name=f"Pay Widget {tag}", qty="10")
    customer = await make_customer(client, headers, code=f"CPAY-C-{tag}", name=f"Pay Cust {tag}")
    for quantity in ("2", "1"):
        sale = await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CUSTOMER_DEBT",
                "customer_id": customer["id"],
                "items": [{"product_id": product["id"], "quantity": quantity}],
            },
            headers=headers,
        )
        assert sale.status_code == 201, sale.text
    debts = (await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)).json()["data"]
    assert len(debts) == 2
    return customer, debts


@pytest.mark.asyncio
async def test_customer_level_payment_settles_oldest_first(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts = await _two_customer_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "25.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    payments = response.json()["data"]
    # 25.00 splits: 20.00 onto the oldest debt, 5.00 onto the next.
    assert len(payments) == 2
    assert Decimal(payments[0]["amount"]) == Decimal("20.00")
    assert Decimal(payments[1]["amount"]) == Decimal("5.00")
    assert payments[0]["customer_debt_id"] == debts[0]["id"]

    after = (await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)).json()["data"]
    by_id = {row["id"]: row for row in after}
    assert by_id[debts[0]["id"]]["status"] == "PAID"
    assert Decimal(by_id[debts[0]["id"]]["remaining_amount"]) == Decimal("0.00")
    assert by_id[debts[1]["id"]]["status"] == "PARTIAL"
    assert Decimal(by_id[debts[1]["id"]]["remaining_amount"]) == Decimal("5.00")

    history = await client.get(f"/api/v1/customers/{customer['id']}/payments", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["data"]) == 2


@pytest.mark.asyncio
async def test_customer_level_payment_rejects_overpayment(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts = await _two_customer_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "31.00", "payment_method": "CASH"},  # outstanding is 30.00
        headers=headers,
    )
    assert response.status_code == 422
    assert "exceeds" in response.text


@pytest.mark.asyncio
async def test_customer_level_payment_requires_permission(client, db_session):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts = await _two_customer_debts(client, headers, tag)

    await create_user_with_role(
        db_session,
        email=f"cpay-{tag}@example.com",
        password="cpaypass1",
        role_name=f"Customer Pay Viewer {tag}",
        permissions=["customer.view"],
    )
    await db_session.commit()
    viewer = await login(client, f"cpay-{tag}@example.com", "cpaypass1")
    viewer_headers = {"Authorization": f"Bearer {viewer['access_token']}"}

    denied = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403


async def _supplier_with_two_debts(client, headers, tag: str):
    """Supplier with two open stock-in debts: 15.00 then 5.00 remaining."""
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": f"SPAY-{tag}", "name": f"Pay Supplier {tag}", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"SPAY-CAT-{tag}", "name": f"Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"SPAY-P-{tag}",
                "name": f"Pay Product {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
            },
            headers=headers,
        )
    ).json()["data"]
    for paid in ("5.00", "15.00"):
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
    debts = (await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)).json()["data"]
    assert len(debts) == 2
    return supplier, debts


@pytest.mark.asyncio
async def test_supplier_level_payment_settles_oldest_first(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    supplier, debts = await _supplier_with_two_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "17.00", "payment_method": "BANK_QR"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    payments = response.json()["data"]
    # 17.00 splits: 15.00 onto the oldest debt, 2.00 onto the next.
    assert len(payments) == 2
    assert Decimal(payments[0]["amount"]) == Decimal("15.00")
    assert Decimal(payments[1]["amount"]) == Decimal("2.00")

    after = (await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)).json()["data"]
    by_id = {row["id"]: row for row in after}
    assert by_id[debts[0]["id"]]["status"] == "PAID"
    assert Decimal(by_id[debts[1]["id"]]["remaining_amount"]) == Decimal("3.00")

    over = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "3.01", "payment_method": "CASH"},
        headers=headers,
    )
    assert over.status_code == 422
