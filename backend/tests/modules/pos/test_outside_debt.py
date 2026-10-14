"""Outside debt recorded at POS checkout (spec: debts without a source invoice).

The cashier types in an old debt the customer already owed (paper debt book /
another shop). It must never change the sale's own totals, has no source sale,
appears in the customer debt list and the Debit Report, and is collectible
through the normal debt-payment flow.
"""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers, create_user_with_role, login


async def _checkout_with_outside_debt(
    client,
    headers,
    *,
    sku: str = "OUT-1",
    outside: str = "50.00",
    product_headers=None,
    **extra,
):
    """2 × 10.00 paid in full, plus an outside debt typed at checkout.

    ``product_headers`` seeds the product with a different (privileged) user so
    a test can isolate the *sale* permission."""
    product = await make_stocked_product(
        client,
        product_headers or headers,
        sku=sku,
        name="Outside Debt Widget",
        qty="10",
    )
    payload = {
        "payment_method": "CASH",
        "amount_received": "100.00",
        "items": [{"product_id": product["id"], "quantity": "2"}],
        "outside_debt": outside,
        **extra,
    }
    return await client.post("/api/v1/pos/sales", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_outside_debt_is_recorded_separately_from_the_sale(client):
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C1", name="Notebook Debtor")

    response = await _checkout_with_outside_debt(client, headers, customer_id=customer["id"])
    assert response.status_code == 201, response.text
    sale = response.json()["data"]

    # The sale itself is untouched: 2 × 10.00, paid in full, no sale debt.
    assert Decimal(sale["grand_total"]) == Decimal("20.00")
    assert Decimal(sale["paid_amount"]) == Decimal("20.00")
    assert Decimal(sale["debt_amount"]) == Decimal("0.00")
    assert sale["outside_debt_no"].startswith("OD-")

    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"]
    assert len(debts) == 1
    outside = debts[0]
    assert outside["sale_id"] is None
    assert outside["invoice_no"] == sale["outside_debt_no"]
    assert Decimal(outside["original_amount"]) == Decimal("50.00")
    assert Decimal(outside["remaining_amount"]) == Decimal("50.00")
    assert outside["status"] == "UNPAID"
    # No source invoice → the debt's own created date is the document date.
    assert outside["date"]


@pytest.mark.asyncio
async def test_outside_debt_appears_in_the_debt_report(client):
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C2", name="Report Debtor")
    response = await _checkout_with_outside_debt(
        client, headers, sku="OUT-2", customer_id=customer["id"]
    )
    assert response.status_code == 201, response.text
    reference = response.json()["data"]["outside_debt_no"]

    report = await client.get(
        "/api/v1/reports/customer-debts",
        params={"customer_id": customer["id"]},
        headers=headers,
    )
    assert report.status_code == 200, report.text
    rows = report.json()["data"]
    assert [row["invoice_no"] for row in rows] == [reference]
    row = rows[0]
    assert Decimal(row["remaining_amount"]) == Decimal("50.00")
    assert row["date"]
    # Attributed to the user who recorded it (there is no sale cashier).
    assert row["user_id"]
    assert row["user_name"]


@pytest.mark.asyncio
async def test_khr_outside_debt_keeps_its_document_currency(client):
    """A KHR sale records a KHR outside debt so reports never mix currencies."""
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C3", name="Riel Debtor")
    response = await _checkout_with_outside_debt(
        client,
        headers,
        sku="OUT-3",
        outside="500000",
        customer_id=customer["id"],
        currency="KHR",
        exchange_rate="4000",
        # 2 × 10.00 USD at 4,000 → 80,000 KHR; pay it so the only debt is the
        # outside one under test.
        amount_received="80000",
    )
    assert response.status_code == 201, response.text
    sale = response.json()["data"]
    assert Decimal(sale["debt_amount"]) == Decimal("0.00")

    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"]
    outside = next(row for row in debts if row["sale_id"] is None)
    assert outside["currency"] == "KHR"
    assert Decimal(outside["exchange_rate"]) == Decimal("4000")
    assert Decimal(outside["remaining_amount"]) == Decimal("500000")


@pytest.mark.asyncio
async def test_outside_debt_requires_a_registered_customer(client):
    headers = await admin_headers(client)
    # No customer_id → the backend resolves the walk-in customer.
    response = await _checkout_with_outside_debt(client, headers, sku="OUT-4")
    assert response.status_code == 422, response.text
    assert "outside_debt" in response.text


@pytest.mark.asyncio
async def test_outside_debt_requires_the_debt_sale_permission(client, db_session):
    admin = await admin_headers(client)
    # The customer is created by an admin: this test is about the sale only.
    customer = await make_customer(client, admin, code="OUT-C5", name="Perm Debtor")

    await create_user_with_role(
        db_session,
        email="outside-cashier@example.com",
        password="cashierpass1",
        role_name="Outside Cashier",
        permissions=["pos.access"],
    )
    await db_session.commit()
    data = await login(client, "outside-cashier@example.com", "cashierpass1")
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    response = await _checkout_with_outside_debt(
        client,
        headers,
        sku="OUT-5",
        customer_id=customer["id"],
        product_headers=admin,
    )
    assert response.status_code == 403, response.text
    # Nothing was recorded: the whole checkout is rejected atomically.
    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=admin)
    ).json()["data"]
    assert debts == []


@pytest.mark.asyncio
async def test_outside_debt_survives_a_sale_edit(client):
    """Editing the invoice must not touch a debt that has no source sale."""
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C6", name="Edit Debtor")
    response = await _checkout_with_outside_debt(
        client, headers, sku="OUT-6", customer_id=customer["id"]
    )
    assert response.status_code == 201, response.text
    sale = response.json()["data"]
    product_id = sale["items"][0]["product_id"]

    edited = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={
            "items": [{"product_id": product_id, "quantity": "3", "unit_price": "10.00"}],
            "payment_method": "CASH",
            "amount_received": "100.00",
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text

    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"]
    assert len(debts) == 1
    assert Decimal(debts[0]["remaining_amount"]) == Decimal("50.00")


@pytest.mark.asyncio
async def test_outside_debt_can_be_collected_like_any_other_debt(client):
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C7", name="Collect Debtor")
    response = await _checkout_with_outside_debt(
        client, headers, sku="OUT-7", customer_id=customer["id"]
    )
    assert response.status_code == 201, response.text
    debt = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"][0]

    payment = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "20.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["data"]["payment_type"] == "CUSTOMER_DEBT_PAYMENT"

    after = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"][0]
    assert Decimal(after["remaining_amount"]) == Decimal("30.00")
    assert after["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_outside_debt_is_absent_when_not_typed(client):
    """Zero (the default) records nothing — plain checkouts are unchanged."""
    headers = await admin_headers(client)
    customer = await make_customer(client, headers, code="OUT-C8", name="Plain Debtor")
    response = await _checkout_with_outside_debt(
        client, headers, sku="OUT-8", outside="0", customer_id=customer["id"]
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["outside_debt_no"] is None
    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"]
    assert debts == []
