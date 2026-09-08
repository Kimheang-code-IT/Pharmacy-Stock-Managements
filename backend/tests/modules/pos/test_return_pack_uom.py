"""Sale return restock with a Pricing pack UOM (spec §2.1.3 / §2.1.7).

A line sold in a pack UOM (factor_to_base = 10) must restock factor × the
returned line quantity in base units — never the raw line quantity.
"""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of, make_customer
from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_pack_product(client, headers, *, sku: str, name: str) -> dict:
    pack = (
        await client.post(
            "/api/v1/uoms",
            json={"code": f"PK{sku[-3:]}", "name": f"Pack {sku}", "symbol": "pkt"},
            headers=headers,
        )
    ).json()["data"]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"C-{sku}", "name": f"Cat {sku}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
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
                        "factor_to_base": "10",
                        "sale_price": "110.00",
                        "is_default_sale": False,
                    },
                ],
            },
            headers=headers,
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "100.00",
            "items": [{"product_id": product["id"], "quantity": "20", "unit_cost": "5.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    return product


@pytest.mark.asyncio
async def test_pack_sale_and_return_restock_in_base_units(client):
    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="PRU-1", name="Pack Return Widget")
    customer = await make_customer(client, headers, code="CUS-PRU-1", name="Pack Return Customer")
    pack_row = next(
        row for row in product["uomConversions"] if row["uom_id"] != str(DEFAULT_UOM_ID)
    )

    # Sell 2 packs (= 20 base units) at the pack price.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "customer_id": customer["id"],
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [
                {
                    "product_id": product["id"],
                    "uom_id": pack_row["uom_id"],
                    "factor_to_base": pack_row["factor_to_base"],
                    "quantity": "2",
                    "unit_price": "110.00",
                }
            ],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    assert Decimal(sale_data["grand_total"]) == Decimal("220.00")
    assert await balance_of(client, headers, product["id"]) == Decimal("0.0000")
    sale_item_id = sale_data["items"][0]["id"]

    # Return 1 pack WITH restock → +10 base units, refund 110.00.
    response = await client.post(
        f"/api/v1/pos/sales/{sale_data['id']}/return",
        json={
            "reason": "One pack returned",
            "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sale_return = response.json()["data"]
    assert Decimal(sale_return["refund_amount"]) == Decimal("110.00")
    assert await balance_of(client, headers, product["id"]) == Decimal("10.0000")

    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=SALE_RETURN", headers=headers
    )
    assert Decimal(movements.json()["data"][0]["quantity_delta"]) == Decimal("10.0000")
