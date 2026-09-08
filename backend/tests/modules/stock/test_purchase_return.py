"""Purchase Return (return to supplier) — spec: Purchase Return Transaction.

One transaction: PRT- document, PURCHASE_RETURN stock movement, supplier-debt
reduction (or supplier credit when the purchase was fully paid), immutable
return docs, and a full rollback when any line fails.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_product(client, headers, *, sku: str, name: str) -> dict:
    """A product with NO stock yet (the tests stock it explicitly)."""
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"C-{sku}", "name": f"Cat {sku}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": name,
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "10.00",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_supplier(client, headers, code: str) -> dict:
    response = await client.post("/api/v1/suppliers", json={"name": f"Supplier {code}"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _stock_in(client, headers, items, *, supplier_id=None, paid=None) -> dict:
    """items: [{product_id, quantity, unit_cost}]; fully paid unless `paid`."""
    total = sum(Decimal(i["quantity"]) * Decimal(i["unit_cost"]) for i in items)
    payload = {
        "items": items,
        "paid_amount": str(paid if paid is not None else total),
    }
    if supplier_id is not None:
        payload["supplier_id"] = supplier_id
    response = await client.post("/api/v1/stock/in", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _balance(client, headers, product_id) -> Decimal:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    return Decimal(response.json()["data"]["quantity"])


async def _supplier_debt(client, headers, supplier_id) -> dict | None:
    response = await client.get(f"/api/v1/suppliers/{supplier_id}/debts", headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    return rows[0] if rows else None


@pytest.mark.asyncio
async def test_purchase_return_reduces_stock_and_debt(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="PRT-1", name="Return Supplier Widget")
    supplier = await _make_supplier(client, headers, "PRT-1")
    stock_in = await _stock_in(
        client,
        headers,
        [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        supplier_id=supplier["id"],
        paid="0.00",
    )
    item_id = stock_in["items"][0]["id"]

    response = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "Damaged in shipment",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "4"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]

    assert data["return_no"].startswith("PRT-")
    assert data["document_no"] == stock_in["document_no"]
    assert Decimal(data["refund_amount"]) == Decimal("8.00")
    # The purchase was unpaid, so the whole refund reduces the open debt.
    assert Decimal(data["debt_reduction"]) == Decimal("8.00")
    assert Decimal(data["credit_amount"]) == Decimal("0.00")
    assert Decimal(data["items"][0]["line_refund"]) == Decimal("8.00")

    # Stock OUT of exactly 4 units.
    assert await _balance(client, headers, product["id"]) == Decimal("6.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=PURCHASE_RETURN", headers=headers
    )
    assert movements.json()["meta"]["total"] == 1
    assert Decimal(movements.json()["data"][0]["quantity_delta"]) == Decimal("-4.0000")
    assert movements.json()["data"][0]["document_no"] == data["return_no"]

    debt = await _supplier_debt(client, headers, supplier["id"])
    assert Decimal(debt["remaining_amount"]) == Decimal("12.00")
    assert debt["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_purchase_return_rejects_over_return(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="PRT-2", name="Over Return Widget")
    stock_in = await _stock_in(
        client, headers, [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}]
    )
    item_id = stock_in["items"][0]["id"]

    # More than received.
    response = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "Too much",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "11"}],
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert await _balance(client, headers, product["id"]) == Decimal("10.0000")

    # Return 6, then trying 6 more exceeds the returnable (4 left).
    first = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "First batch",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "6"}],
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "Second batch",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "5"}],
        },
        headers=headers,
    )
    assert second.status_code == 422, second.text
    assert await _balance(client, headers, product["id"]) == Decimal("4.0000")


@pytest.mark.asyncio
async def test_purchase_return_cannot_exceed_available_stock(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="PRT-3", name="Stock Limited Widget")
    stock_in = await _stock_in(
        client, headers, [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}]
    )
    item_id = stock_in["items"][0]["id"]

    # Sell 8 of the 10 units via POS so only 2 remain available.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{"product_id": product["id"], "quantity": "8"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    response = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "More than available",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "3"}],
        },
        headers=headers,
    )
    assert response.status_code == 409, response.text
    assert await _balance(client, headers, product["id"]) == Decimal("2.0000")


@pytest.mark.asyncio
async def test_purchase_return_fully_paid_purchase_records_supplier_credit(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="PRT-4", name="Paid Return Widget")
    supplier = await _make_supplier(client, headers, "PRT-4")
    stock_in = await _stock_in(
        client,
        headers,
        [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        supplier_id=supplier["id"],
    )
    item_id = stock_in["items"][0]["id"]

    response = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "Wrong product",
            "lines": [{"stock_transaction_item_id": item_id, "quantity": "10"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert Decimal(data["debt_reduction"]) == Decimal("0.00")
    assert Decimal(data["credit_amount"]) == Decimal("20.00")

    payments = await client.get(f"/api/v1/suppliers/{supplier['id']}/payments", headers=headers)
    assert payments.status_code == 200, payments.text
    credits = [
        row
        for row in payments.json()["data"]
        if row.get("payment_type") == "SUPPLIER_RETURN_CREDIT"
    ]
    assert len(credits) == 1
    assert Decimal(credits[0]["amount"]) == Decimal("20.00")
    assert credits[0]["reference_no"] == data["return_no"]


@pytest.mark.asyncio
async def test_purchase_return_rolls_back_when_any_line_fails(client, db_session):
    """A failure on a later line (mid-transaction) must undo the earlier
    lines' stock movements, quantities, and the return document itself."""
    from app.modules.stock.models import PurchaseReturn, StockBalance, StockMovement

    headers = await admin_headers(client)
    product_a = await _make_product(client, headers, sku="PRT-5", name="Rollback A")
    product_b = await _make_product(client, headers, sku="PRT-6", name="Rollback B")
    stock_in = await _stock_in(
        client,
        headers,
        [
            {"product_id": product_a["id"], "quantity": "10", "unit_cost": "2.00"},
            {"product_id": product_b["id"], "quantity": "10", "unit_cost": "3.00"},
        ],
    )
    line_a, line_b = stock_in["items"][0], stock_in["items"][1]

    # Product B's stock is drained via POS so its line still has returnable
    # qty but the PURCHASE_RETURN movement will fail — after line A has
    # already mutated stock.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{"product_id": product_b["id"], "quantity": "10"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    response = await client.post(
        f"/api/v1/stock/in/{stock_in['id']}/return",
        json={
            "reason": "Second line must fail and roll everything back",
            "lines": [
                {"stock_transaction_item_id": line_a["id"], "quantity": "3"},
                {"stock_transaction_item_id": line_b["id"], "quantity": "1"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 409, response.text

    # Nothing persisted: no return document, no movement, no balance change.
    returns = (
        await db_session.execute(
            select(PurchaseReturn).where(PurchaseReturn.stock_transaction_id == stock_in["id"])
        )
    ).scalars().all()
    assert returns == []
    movements = (
        await db_session.execute(
            select(StockMovement).where(
                StockMovement.product_id.in_([product_a["id"], product_b["id"]]),
                StockMovement.movement_type == "PURCHASE_RETURN",
            )
        )
    ).scalars().all()
    assert movements == []
    balance_a = await db_session.get(StockBalance, product_a["id"])
    assert Decimal(balance_a.quantity) == Decimal("10.0000")
