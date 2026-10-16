"""Sale edit (PATCH /pos/sales/{id}): reverse stock, reapply lines, recalc debt."""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of, make_customer, make_stocked_product
from tests.utils import admin_headers


@pytest.mark.asyncio
async def test_sale_edit_reverses_and_reapplies_stock(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="EDIT-1", name="Edit Widget")

    created = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "3"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sale = created.json()["data"]
    assert await balance_of(client, headers, product["id"]) == Decimal("7.0000")

    edited = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "2", "unit_price": "10.00"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert Decimal(updated["subtotal"]) == Decimal("20.00")
    assert Decimal(updated["grand_total"]) == Decimal("20.00")
    # 7 + 3 (reversal) - 2 (new line) = 8
    assert await balance_of(client, headers, product["id"]) == Decimal("8.0000")

    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}", headers=headers
    )
    types = [row["movement_type"] for row in movements.json()["data"]]
    assert "SALE_RETURN" in types
    assert types.count("SALE") == 2


@pytest.mark.asyncio
async def test_sale_edit_recalculates_customer_debt(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="EDIT-2", name="Edit Debt Widget")
    customer = await make_customer(client, headers, code="EDIT-C", name="Edit Buyer")

    created = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "0",
            "items": [{"product_id": product["id"], "quantity": "3"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sale = created.json()["data"]
    assert Decimal(sale["debt_amount"]) == Decimal("30.00")

    edited = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "1", "unit_price": "10.00"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert Decimal(updated["grand_total"]) == Decimal("10.00")
    assert Decimal(updated["debt_amount"]) == Decimal("10.00")

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    assert debts.status_code == 200, debts.text
    debt = debts.json()["data"][0]
    assert Decimal(debt["remaining_amount"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_sale_edit_corrects_customer_payment_method_and_paid(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="EDIT-3", name="Edit Tender Widget")
    buyer_a = await make_customer(client, headers, code="EDIT-A", name="Buyer A")
    buyer_b = await make_customer(client, headers, code="EDIT-B", name="Buyer B")

    created = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": buyer_a["id"],
            "amount_received": "0",
            "items": [{"product_id": product["id"], "quantity": "2", "unit_price": "10.00"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sale = created.json()["data"]
    assert Decimal(sale["debt_amount"]) == Decimal("20.00")

    items = [{"product_id": product["id"], "quantity": "2", "unit_price": "10.00"}]
    edited = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={
            "customer_id": buyer_b["id"],
            "payment_method": "CASH",
            "amount_received": "5.00",
            "items": items,
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert updated["customer_id"] == buyer_b["id"]
    assert Decimal(updated["paid_amount"]) == Decimal("5.00")
    assert Decimal(updated["debt_amount"]) == Decimal("15.00")

    # The debt moved to the corrected customer with the new balance.
    debts_b = await client.get(f"/api/v1/customers/{buyer_b['id']}/debts", headers=headers)
    assert debts_b.status_code == 200, debts_b.text
    moved = debts_b.json()["data"]
    assert len(moved) == 1
    assert Decimal(moved[0]["remaining_amount"]) == Decimal("15.00")

    debts_a = await client.get(f"/api/v1/customers/{buyer_a['id']}/debts", headers=headers)
    assert debts_a.json()["data"] == []

    # Reducing the paid amount books a refund ledger entry (admin has pos.refund).
    refunded = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={"amount_received": "0", "items": items},
        headers=headers,
    )
    assert refunded.status_code == 200, refunded.text
    after = refunded.json()["data"]
    assert Decimal(after["paid_amount"]) == Decimal("0.00")
    assert Decimal(after["debt_amount"]) == Decimal("20.00")


@pytest.mark.asyncio
async def test_sale_edit_keeps_khr_snapshot(client):
    """A KHR invoice is STORED on KHR: after an edit the document, its receipt,
    its report row and the customer debt all keep the KHR currency + rate —
    never re-based to USD."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(
        client, headers, sku=f"EDITK-{tag}", name=f"Edit KHR {tag}"
    )
    customer = await make_customer(
        client, headers, code=f"EDITK-C-{tag}", name=f"KHR Buyer {tag}"
    )

    created = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "currency": "KHR",
            "exchange_rate": "41000",
            "items": [{"product_id": product["id"], "quantity": "1", "unit_price": "410000"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sale = created.json()["data"]
    assert sale["currency"] == "KHR"

    edited = await client.patch(
        f"/api/v1/pos/sales/{sale['id']}",
        json={
            "currency": "KHR",
            "exchange_rate": "41000",
            "items": [{"product_id": product["id"], "quantity": "1", "unit_price": "820000"}],
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert updated["currency"] == "KHR"
    assert Decimal(updated["exchange_rate"]) == Decimal("41000")
    assert Decimal(updated["grand_total"]) == Decimal("820000.00")

    # Receipt + grouped report row + customer debt all follow the KHR snapshot.
    receipt = await client.get(f"/api/v1/pos/sales/{sale['id']}/receipt", headers=headers)
    assert receipt.json()["data"]["currency"] == "KHR"

    report = await client.get(
        f"/api/v1/reports/sales?q={sale['invoice_no']}", headers=headers
    )
    assert report.status_code == 200, report.text
    row = report.json()["data"][0]
    assert row["currency"] == "KHR"
    assert Decimal(str(row["exchange_rate"])) == Decimal("41000")
    assert Decimal(row["grand_total"]) == Decimal("820000.00")

    debts = (
        await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    ).json()["data"]
    assert debts and debts[0]["currency"] == "KHR"
    assert Decimal(debts[0]["remaining_amount"]) == Decimal("820000.00")

