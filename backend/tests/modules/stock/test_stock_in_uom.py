"""Stock In with Pricing Original UOM (spec §2.1.3 / §2.1.5).

qty and unit_cost are per the SELECTED Pricing UOM; the stock mutation,
balance, and ledger quantities are converted to the product base UOM via
factor_to_base. Unpaid/partial purchases still create the supplier debt in
the same transaction.
"""

from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_uom(client, headers, code: str) -> dict:
    response = await client.post(
        "/api/v1/uoms", json={"code": code, "name": f"Unit {code}", "symbol": code.lower()}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_pack_product(client, headers, *, sku: str, name: str, factor: str = "10") -> dict:
    pack = await _make_uom(client, headers, f"PKT{sku[-3:]}")
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
            "selling_price": "12.00",
            "uom_conversions": [
                {
                    "uom_id": str(DEFAULT_UOM_ID),
                    "factor_to_base": "1",
                    "sale_price": "12.00",
                    "is_default_sale": True,
                },
                {
                    "uom_id": pack["id"],
                    "factor_to_base": factor,
                    "sale_price": "110.00",
                    "is_default_sale": False,
                },
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    product = response.json()["data"]
    return product


async def _make_supplier(client, headers, code: str) -> dict:
    response = await client.post("/api/v1/suppliers", json={"name": f"Supplier {code}"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_stock_in_with_pricing_uom_converts_to_base(client):
    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="SIU-1", name="Pack Widget")
    pack_uom = next(
        row for row in product["uomConversions"] if row["uom_id"] != str(DEFAULT_UOM_ID)
    )

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "200.00",
            "items": [
                {
                    "product_id": product["id"],
                    "uom_id": pack_uom["uom_id"],
                    "factor_to_base": pack_uom["factor_to_base"],
                    "quantity": "2",
                    "unit_cost": "100.00",
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    stock_in = response.json()["data"]

    # Line total is per the selected UOM (2 packs × 100.00)…
    assert Decimal(stock_in["total_amount"]) == Decimal("200.00")
    # …but the ledger keeps base units: 2 packs × 10 = 20 Each at 10.00 each.
    item = stock_in["items"][0]
    assert Decimal(item["quantity"]) == Decimal("20.0000")
    assert Decimal(item["unit_cost"]) == Decimal("10.00")
    assert Decimal(item["line_total"]) == Decimal("200.00")

    assert await _balance(client, headers, product["id"]) == Decimal("20.0000")

    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=STOCK_IN", headers=headers
    )
    assert Decimal(movements.json()["data"][0]["quantity_delta"]) == Decimal("20.0000")
    assert Decimal(movements.json()["data"][0]["unit_cost"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_stock_in_with_pricing_uom_creates_supplier_debt_same_transaction(client):
    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="SIU-2", name="Pack Widget 2")
    supplier = await _make_supplier(client, headers, "SIU-2")
    pack_uom = next(
        row for row in product["uomConversions"] if row["uom_id"] != str(DEFAULT_UOM_ID)
    )

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "50.00",
            "items": [
                {
                    "product_id": product["id"],
                    "uom_id": pack_uom["uom_id"],
                    "quantity": "2",
                    "unit_cost": "100.00",
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    stock_in = response.json()["data"]
    assert stock_in["debt_created"] is True

    debts = await client.get(
        f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers
    )
    assert debts.status_code == 200, debts.text
    rows = debts.json()["data"]
    assert len(rows) == 1
    assert Decimal(rows[0]["original_amount"]) == Decimal("200.00")
    assert Decimal(rows[0]["remaining_amount"]) == Decimal("150.00")


@pytest.mark.asyncio
async def test_stock_in_rejects_non_pricing_uom(client):
    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="SIU-3", name="Pack Widget 3")
    other_uom = await _make_uom(client, headers, "OTH3")

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "200.00",
            "items": [
                {
                    "product_id": product["id"],
                    "uom_id": other_uom["id"],
                    "quantity": "2",
                    "unit_cost": "100.00",
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert await _balance(client, headers, product["id"]) == Decimal("0.0000")


async def _balance(client, headers, product_id) -> Decimal:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    return Decimal(response.json()["data"]["quantity"])
