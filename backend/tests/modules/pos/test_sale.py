"""POS sale completion: atomicity, payments, discounts, oversell (spec 2.1.7)."""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import (
    balance_of,
    make_customer,
    make_stocked_product,
)
from tests.utils import admin_headers, create_user_with_role, login


async def _cash_sale(client, headers, product_id, *, quantity="3", amount="100.00", **extra):
    payload = {
        "payment_method": "CASH",
        "amount_received": amount,
        "items": [{"product_id": product_id, "quantity": quantity}],
        **extra,
    }
    return await client.post("/api/v1/pos/sales", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_cash_sale_atomic_completion(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-1", name="POS Widget")

    response = await _cash_sale(client, headers, product["id"], amount="50.00")
    assert response.status_code == 201, response.text
    sale = response.json()["data"]

    import re

    assert re.fullmatch(r"[A-Z]+-\d{6,8}", sale["invoice_no"]), sale["invoice_no"]
    assert Decimal(sale["subtotal"]) == Decimal("30.00")
    assert Decimal(sale["grand_total"]) == Decimal("30.00")
    assert Decimal(sale["paid_amount"]) == Decimal("30.00")
    assert Decimal(sale["debt_amount"]) == Decimal("0.00")
    assert sale["payment_status"] == "PAID"
    assert sale["sale_status"] == "COMPLETED"
    assert Decimal(sale["change_amount"]) == Decimal("20.00")
    assert Decimal(sale["items"][0]["unit_cost"]) == Decimal("2.00")

    # Stock reduced by the sale and movement recorded.
    assert await balance_of(client, headers, product["id"]) == Decimal("7.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=SALE", headers=headers
    )
    assert movements.json()["meta"]["total"] == 1
    assert Decimal(movements.json()["data"][0]["quantity_delta"]) == Decimal("-3.0000")

    # Sale is listed and retrievable.
    listing = await client.get(f"/api/v1/pos/sales?q={sale['invoice_no']}", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] == 1
    assert listing.json()["data"][0]["id"] == sale["id"]
    detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["invoice_no"] == sale["invoice_no"]


@pytest.mark.asyncio
async def test_bank_qr_sale_records_reference(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-QR", name="QR Widget")
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "BANK_QR",
            "amount_received": "10.00",
            "reference_no": "TX-99",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sale = response.json()["data"]
    assert sale["payment_status"] == "PAID"
    assert Decimal(sale["change_amount"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_cash_sale_rejects_insufficient_amount(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-2", name="Poor Pay Widget")
    response = await _cash_sale(client, headers, product["id"], amount="5.00")
    assert response.status_code == 422
    # Nothing persisted: stock unchanged.
    assert await balance_of(client, headers, product["id"]) == Decimal("10.0000")


@pytest.mark.asyncio
async def test_sale_rejects_oversell(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-3", name="Scarce Widget")
    response = await _cash_sale(client, headers, product["id"], quantity="11", amount="500.00")
    assert response.status_code == 409
    assert await balance_of(client, headers, product["id"]) == Decimal("10.0000")


@pytest.mark.asyncio
async def test_sale_rejects_duplicate_product_line(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-4", name="Dup Widget")
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [
                {"product_id": product["id"], "quantity": "1"},
                {"product_id": product["id"], "quantity": "1"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sale_rejects_unknown_product(client):
    headers = await admin_headers(client)
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": "1"}],
        },
        headers=headers,
    )
    assert response.status_code == 404


CASHIER_EMAIL = "cashier-nodisc@example.com"
CASHIER_PASSWORD = "cashierpass1"


@pytest.fixture
async def cashier_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=CASHIER_EMAIL,
        password=CASHIER_PASSWORD,
        role_name="Cashier NoDiscount",
        permissions=["pos.access", "pos.print"],
    )
    await db_session.commit()
    data = await login(client, CASHIER_EMAIL, CASHIER_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.mark.asyncio
async def test_discount_requires_permission(client, cashier_headers):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-5", name="Discount Widget")

    denied = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "1", "discount_amount": "1.00"}],
        },
        headers=cashier_headers,
    )
    assert denied.status_code == 409

    # Admin (all permissions) may discount.
    allowed = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "1", "discount_amount": "1.00"}],
        },
        headers=headers,
    )
    assert allowed.status_code == 201, allowed.text
    sale = allowed.json()["data"]
    assert Decimal(sale["discount_amount"]) == Decimal("1.00")
    assert Decimal(sale["grand_total"]) == Decimal("9.00")


@pytest.mark.asyncio
async def test_discount_respects_maximum_setting(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-6", name="Capped Widget")

    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    db_session.add(
        SystemSetting(group_name="pos", key="pos.maximum_discount", value={"v": 5})
    )
    await db_session.commit()
    try:
        response = await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CASH",
                "amount_received": "100.00",
                "items": [{"product_id": product["id"], "quantity": "1", "discount_amount": "2.00"}],
            },
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        # The setting is global state in the shared test database — remove it so
        # later tests keep the default (no cap).
        await db_session.execute(
            delete(SystemSetting).where(
                SystemSetting.group_name == "pos", SystemSetting.key == "pos.maximum_discount"
            )
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_debt_sale_requires_registered_customer(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-7", name="Walkin Debt Widget")
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert await balance_of(client, headers, product["id"]) == Decimal("10.0000")


@pytest.mark.asyncio
async def test_debt_sale_creates_debt_with_partial_deposit(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="POS-8", name="Debt Widget")
    customer = await make_customer(client, headers, code="CUS-POS-1", name="Debt Buyer")

    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "4.00",
            "due_date": "2026-12-31",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sale = response.json()["data"]
    assert Decimal(sale["paid_amount"]) == Decimal("4.00")
    assert Decimal(sale["debt_amount"]) == Decimal("6.00")
    assert sale["payment_status"] == "PARTIAL"

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    assert debts.status_code == 200, debts.text
    debt_rows = debts.json()["data"]
    assert len(debt_rows) == 1
    debt = debt_rows[0]
    assert Decimal(debt["original_amount"]) == Decimal("10.00")
    assert Decimal(debt["paid_amount"]) == Decimal("4.00")
    assert Decimal(debt["remaining_amount"]) == Decimal("6.00")
    assert debt["status"] == "PARTIAL"
    assert debt["invoice_no"] == sale["invoice_no"]

    # Stock moved even though the sale is on credit.
    assert await balance_of(client, headers, product["id"]) == Decimal("9.0000")
