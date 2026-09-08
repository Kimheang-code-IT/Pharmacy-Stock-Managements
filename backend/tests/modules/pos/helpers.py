"""Shared helpers for POS module tests."""

from decimal import Decimal

from tests.utils import DEFAULT_UOM_ID



async def make_stocked_product(client, headers, *, sku: str, name: str, qty: str = "10", unit_cost: str = "2.00", selling_price: str = "10.00") -> dict:
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
                "selling_price": selling_price,
            },
            headers=headers,
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": str(Decimal(unit_cost) * Decimal(qty)),
            "items": [{"product_id": product["id"], "quantity": qty, "unit_cost": unit_cost}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    return product


async def make_customer(client, headers, *, code: str, name: str) -> dict:
    response = await client.post(
        "/api/v1/customers",
        json={"code": code, "name": name, "phone": "0123456789", "status": "ACTIVE"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def complete_sale(client, headers, *, items, payment_method="CASH", amount_received="100.00", **extra) -> dict:
    payload = {
        "payment_method": payment_method,
        "amount_received": amount_received,
        "items": items,
        **extra,
    }
    return payload


async def balance_of(client, headers, product_id) -> Decimal:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    return Decimal(response.json()["data"]["quantity"])
