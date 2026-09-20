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
