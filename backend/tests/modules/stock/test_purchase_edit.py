"""Purchase edit (PATCH /stock/in/{id}): reverse receipt, reapply lines, totals."""

from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_product(client, headers, sku: str) -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"C-{sku}", "name": f"Cat {sku}"}, headers=headers
        )
    ).json()["data"]
    return (
        await client.post(
            "/api/v1/products",
            json={
                "sku": sku,
                "name": f"Widget {sku}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
            },
            headers=headers,
        )
    ).json()["data"]


async def _balance(client, headers, product_id) -> Decimal:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    return Decimal(response.json()["data"]["quantity"])


@pytest.mark.asyncio
async def test_purchase_report_exposes_batch_and_expiry_for_edit(client):
    """The purchase Edit form reloads from GET /reports/purchases, so each row
    must carry the original batch no + expiry date of the received lot."""
    headers = await admin_headers(client)
    category = (
        await client.post(
            "/api/v1/categories", json={"code": "C-PE-EXP", "name": "Cat PE-EXP"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": "PE-EXP-1",
                "name": "Expiry Widget",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
                "track_batch": True,
                "expiry_tracking": True,
            },
            headers=headers,
        )
    ).json()["data"]

    created = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "20.00",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "10",
                    "unit_cost": "2.00",
                    "batch_no": "LOT-EDIT-1",
                    "expiry_date": "2030-06-30",
                }
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    document_no = created.json()["data"]["document_no"]

    report = await client.get(
        "/api/v1/reports/purchases", params={"q": document_no}, headers=headers
    )
    assert report.status_code == 200, report.text
    rows = report.json()["data"]
    row = next(item for item in rows if item["document_no"] == document_no)
    assert row["batch_no"] == "LOT-EDIT-1"
    assert row["expiry_date"] == "2030-06-30"


@pytest.mark.asyncio
async def test_purchase_edit_reverses_and_reapplies(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, "PE-1")

    created = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "20.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    doc = created.json()["data"]
    assert await _balance(client, headers, product["id"]) == Decimal("10.0000")

    edited = await client.patch(
        f"/api/v1/stock/in/{doc['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "6", "unit_cost": "2.00"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert Decimal(updated["total_amount"]) == Decimal("12.00")
    assert await _balance(client, headers, product["id"]) == Decimal("6.0000")


@pytest.mark.asyncio
async def test_purchase_edit_recalculates_supplier_debt(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, "PE-2")
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": "SUP-PE-2", "name": "Edit Supplier", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]

    created = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "0",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    doc = created.json()["data"]

    edited = await client.patch(
        f"/api/v1/stock/in/{doc['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "4", "unit_cost": "2.00"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()["data"]
    assert Decimal(updated["total_amount"]) == Decimal("8.00")
    assert Decimal(updated["paid_amount"]) == Decimal("0.00")
    assert updated["debt_created"] is True


async def _buy_and_sell_8(client, headers, sku: str) -> tuple[dict, dict]:
    """Buy 10 units on supplier credit, then sell 8 via POS so only 2 remain."""
    product = await _make_product(client, headers, sku)
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": f"SUP-{sku}", "name": f"Supplier {sku}", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]
    created = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "0",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    doc = created.json()["data"]
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
    assert await _balance(client, headers, product["id"]) == Decimal("2.0000")
    return product, doc


@pytest.mark.asyncio
async def test_purchase_edit_after_sale_allows_price_change(client):
    """A price/note-only edit must not touch stock (the old logic reversed the
    full original quantity and failed once part of it was sold)."""
    headers = await admin_headers(client)
    product, doc = await _buy_and_sell_8(client, headers, "PE-3")

    edited = await client.patch(
        f"/api/v1/stock/in/{doc['id']}",
        json={
            "note": "Price correction",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.50"}],
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["data"]["total_amount"]) == Decimal("25.00")
    assert await _balance(client, headers, product["id"]) == Decimal("2.0000")


@pytest.mark.asyncio
async def test_purchase_edit_cannot_reduce_below_sold(client):
    headers = await admin_headers(client)
    product, doc = await _buy_and_sell_8(client, headers, "PE-4")

    edited = await client.patch(
        f"/api/v1/stock/in/{doc['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "1", "unit_cost": "2.00"}]},
        headers=headers,
    )
    assert edited.status_code == 422, edited.text
    assert "still in stock" in edited.json()["detail"]["message"].lower()
    assert await _balance(client, headers, product["id"]) == Decimal("2.0000")


@pytest.mark.asyncio
async def test_purchase_edit_increase_receives_extra(client):
    headers = await admin_headers(client)
    product, doc = await _buy_and_sell_8(client, headers, "PE-5")

    edited = await client.patch(
        f"/api/v1/stock/in/{doc['id']}",
        json={"items": [{"product_id": product["id"], "quantity": "12", "unit_cost": "2.00"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert await _balance(client, headers, product["id"]) == Decimal("4.0000")
