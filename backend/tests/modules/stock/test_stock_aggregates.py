"""Stock read aggregates + product history (spec section 2.1.5)."""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of, make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _product_row(client, headers, product_id: str) -> dict:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_product_list_exposes_stock_aggregates(client):
    """stockIn/stockOut/damage derive from movements, not the balance."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"AGG-{tag}", name=f"Agg Widget {tag}", qty="10")
    pid = product["id"]

    # Sell 3 units.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": pid, "quantity": "3"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    # Damage 1 unit.
    damage = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": pid, "quantity": "1", "reason": "dropped"}]},
        headers=headers,
    )
    assert damage.status_code == 201, damage.text

    row = await _product_row(client, headers, pid)
    # Stock in = STOCK_IN(10); sale return not involved yet.
    assert Decimal(row["stock_in_qty"]) == Decimal("10.0000")
    # Stock out = SALE(3).
    assert Decimal(row["stock_out_qty"]) == Decimal("3.0000")
    # Damage = DAMAGE(1).
    assert Decimal(row["damage_qty"]) == Decimal("1.0000")
    # Current stock authoritative: 10 - 3 - 1.
    assert await balance_of(client, headers, pid) == Decimal("6.0000")

    # The list endpoint carries the same aggregates.
    listing = await client.get(f"/api/v1/products?q=AGG-{tag}", headers=headers)
    rows = listing.json()["data"]
    assert len(rows) == 1
    assert Decimal(rows[0]["stock_in_qty"]) == Decimal("10.0000")
    assert Decimal(rows[0]["stock_out_qty"]) == Decimal("3.0000")
    assert Decimal(rows[0]["damage_qty"]) == Decimal("1.0000")
    # The API-mediated image URL field is part of the product DTO.
    assert "image_url" in rows[0]
    assert "expiry_date" in rows[0]


@pytest.mark.asyncio
async def test_product_list_exposes_nearest_expiry_date(client):
    """Expire Date on the stock list is the soonest lot expiry from movements."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = (
        await client.post(
            "/api/v1/categories",
            json={"code": f"C-EXP-{tag}", "name": f"Cat Exp {tag}"},
            headers=headers,
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"EXP-{tag}",
                "name": f"Expiry Widget {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "5.00",
                "expiry_tracking": True,
            },
            headers=headers,
        )
    ).json()["data"]
    pid = product["id"]

    first = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "20.00",
            "items": [{
                "product_id": pid,
                "quantity": "4",
                "unit_cost": "2.00",
                "expiry_date": "2027-06-01",
            }],
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "10.00",
            "items": [{
                "product_id": pid,
                "quantity": "2",
                "unit_cost": "2.00",
                "expiry_date": "2026-12-15",
            }],
        },
        headers=headers,
    )
    assert second.status_code == 201, second.text

    row = await _product_row(client, headers, pid)
    assert row["expiry_date"] == "2026-12-15"

    listing = await client.get(f"/api/v1/products?q=EXP-{tag}", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"][0]["expiry_date"] == "2026-12-15"


@pytest.mark.asyncio
async def test_sale_return_counts_as_stock_in(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"RET-{tag}", name=f"Ret Widget {tag}", qty="5")
    pid = product["id"]

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": pid, "quantity": "2"}],
        },
        headers=headers,
    )
    sale_id = sale.json()["data"]["id"]
    sale_item_id = sale.json()["data"]["items"][0]["id"]

    returned = await client.post(
        f"/api/v1/pos/sales/{sale_id}/return",
        json={"reason": "wrong color", "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": True}]},
        headers=headers,
    )
    assert returned.status_code == 201, returned.text

    row = await _product_row(client, headers, pid)
    assert Decimal(row["stock_in_qty"]) == Decimal("6.0000")  # 5 stocked + 1 returned
    assert Decimal(row["stock_out_qty"]) == Decimal("2.0000")  # sale still counted
    assert await balance_of(client, headers, pid) == Decimal("4.0000")


@pytest.mark.asyncio
async def test_history_type_filters(client):
    """History dialog filters: stock_in | stock_out | damage | all."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"HIST-{tag}", name=f"History Widget {tag}", qty="10")
    pid = product["id"]

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": pid, "quantity": "3"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": pid, "quantity": "1", "reason": "broken"}]},
        headers=headers,
    )
    await client.post(
        "/api/v1/stock/in",
        json={"paid_amount": "10.00", "items": [{"product_id": pid, "quantity": "5", "unit_cost": "2.00"}]},
        headers=headers,
    )

    stock_in = await client.get(f"/api/v1/stock/products/{pid}/history?type=stock_in", headers=headers)
    assert stock_in.status_code == 200, stock_in.text
    rows = stock_in.json()["data"]
    assert len(rows) == 2  # initial stock-in + top-up
    assert all(row["kind"] == "stock_in" for row in rows)
    assert all(row["reference"] and row["user"] for row in rows)

    stock_out = await client.get(f"/api/v1/stock/products/{pid}/history?type=stock_out", headers=headers)
    out_rows = stock_out.json()["data"]
    assert len(out_rows) == 1
    assert out_rows[0]["type"] == "Sale"
    assert Decimal(out_rows[0]["qty"]) == Decimal("-3.0000")

    damage = await client.get(f"/api/v1/stock/products/{pid}/history?type=damage", headers=headers)
    damage_rows = damage.json()["data"]
    assert len(damage_rows) == 1
    assert damage_rows[0]["type"] == "Damage"
    assert damage_rows[0]["note"] == "broken"

    everything = await client.get(f"/api/v1/stock/products/{pid}/history?type=all", headers=headers)
    assert everything.json()["meta"]["total"] == 4

    # Default (no type param) behaves like the full movement history.
    default = await client.get(f"/api/v1/stock/products/{pid}/history", headers=headers)
    assert default.json()["meta"]["total"] == 4


@pytest.mark.asyncio
async def test_history_unknown_type_rejected(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"HBAD-{tag}", name=f"Hist Bad {tag}")
    response = await client.get(
        f"/api/v1/stock/products/{product['id']}/history?type=nonsense", headers=headers
    )
    assert response.status_code == 422
