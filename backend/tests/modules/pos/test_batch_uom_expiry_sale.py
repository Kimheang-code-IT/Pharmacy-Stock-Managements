"""Batch management combined with per-batch sale prices, expiry (FEFO) and
multi-UOM POS sales.

This is the intersection the individual suites do not cover on their own:
`test_batch_pricing.py` sells in the base UOM only, while `test_return_pack_uom.py`
sells a pack UOM with no batches. Here a single product is batch-tracked, has a
PACK pricing UOM (factor_to_base = 10), a DIFFERENT sale price per lot (base and
pack rows), an expired lot with stock, and is sold/returned in packs spanning
two FEFO lots.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of
from tests.utils import DEFAULT_UOM_ID, admin_headers

SOON = (date.today() + timedelta(days=30)).isoformat()
LATER = (date.today() + timedelta(days=180)).isoformat()
PAST = (date.today() - timedelta(days=30)).isoformat()


async def _make_pack_uom(client, headers, tag: str) -> dict:
    response = await client.post(
        "/api/v1/uoms",
        json={"code": f"PK{tag[:3]}", "name": f"Pack {tag}", "symbol": "pkt"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_batch_product(client, headers, tag: str, pack: dict) -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"ZZBU-{tag}", "name": f"ZZBU Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"ZZBU-{tag}",
            "name": f"ZZ Batch Pack Widget {tag}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "12.00",
            "track_batch": True,
            "expiry_tracking": True,
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
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _stock_in(client, headers, product_id, *, qty, unit_cost, batch_no, expiry):
    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": str(Decimal(unit_cost) * Decimal(qty)),
            "items": [
                {
                    "product_id": product_id,
                    "quantity": qty,
                    "unit_cost": unit_cost,
                    "batch_no": batch_no,
                    "expiry_date": expiry,
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def _set_batch_price(client, headers, product_id, *, batch_no, base_price, pack_id, pack_price):
    response = await client.post(
        "/api/v1/products/sale-prices",
        json={
            "productId": product_id,
            "salePrice": base_price,
            "batchNo": batch_no,
            "uomPrices": [
                {
                    "uomId": str(DEFAULT_UOM_ID),
                    "factorToBase": 1,
                    "salePrice": base_price,
                    "isDefaultSale": True,
                },
                {
                    "uomId": pack_id,
                    "factorToBase": 10,
                    "salePrice": pack_price,
                    "isDefaultSale": False,
                },
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def _catalog(client, headers, name: str) -> dict:
    response = await client.get("/api/v1/pos/products/search", params={"q": name}, headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows, "product not found in POS catalog"
    return rows[0]


def _pack_price(card: dict, pack_id: str) -> Decimal | None:
    row = next((r for r in card["uom_conversions"] if str(r["uom_id"]) == pack_id), None)
    return Decimal(str(row["sale_price"])) if row is not None else None


async def _batches(client, headers, product_id) -> list[dict]:
    response = await client.get(
        f"/api/v1/stock/products/{product_id}/batches", params={"status": "All"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_batch_multi_uom_distinct_prices_fefo_expiry(client, db_session):
    """Sell 1 PACK from a product whose lots have different base+pack prices and
    different expiry dates; the pack line must blend per-lot pack prices, skip
    the expired lot, deduct base quantities, and a return must restore them."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    pack = await _make_pack_uom(client, headers, tag)
    product = await _make_batch_product(client, headers, tag, pack)

    # Lot B-1: 5 base @ cost 6, expires SOON. Lot B-2: 10 base @ cost 20, LATER.
    # Lot OLD: 7 base, already expired — must never sell.
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="6.00", batch_no="B-1", expiry=SOON)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-2", expiry=LATER)
    await _stock_in(client, headers, product["id"], qty="7", unit_cost="1.00", batch_no="OLD", expiry=PAST)

    # A DIFFERENT price per lot, with a DIFFERENT pack price too.
    await _set_batch_price(
        client, headers, product["id"], batch_no="B-1", base_price="10.00", pack_id=pack["id"], pack_price="90.00"
    )
    await _set_batch_price(
        client, headers, product["id"], batch_no="B-2", base_price="30.00", pack_id=pack["id"], pack_price="280.00"
    )
    await _set_batch_price(
        client, headers, product["id"], batch_no="OLD", base_price="1.00", pack_id=pack["id"], pack_price="5.00"
    )

    # --- Catalog: FEFO lot B-1 drives the displayed price/stock; expired excluded.
    card = await _catalog(client, headers, product["name"])
    assert card["next_batch_no"] == "B-1"
    assert Decimal(str(card["selling_price"])) == Decimal("10.00")
    assert Decimal(str(card["sellable_stock"])) == Decimal("15")  # 5 + 10, not OLD's 7
    assert _pack_price(card, pack["id"]) == Decimal("90.00")

    # --- Sell 1 pack (= 10 base): 5 from B-1 + 5 from B-2, priced per lot.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [
                {
                    "product_id": product["id"],
                    "uom_id": pack["id"],
                    "factor_to_base": "10",
                    "quantity": "1",
                }
            ],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    data = sale.json()["data"]
    # 5/10 × 90 + 5/10 × 280 = 45 + 140 = 185.00
    assert Decimal(data["grand_total"]) == Decimal("185.00")
    assert Decimal(data["items"][0]["unit_price"]) == Decimal("185.00")
    assert data["items"][0]["uom_id"] == pack["id"]

    from sqlalchemy import select

    from app.modules.pos.models import SaleItemBatch

    rows = (
        await db_session.execute(
            select(SaleItemBatch).where(SaleItemBatch.sale_item_id == uuid.UUID(data["items"][0]["id"]))
        )
    ).scalars().all()
    by_batch = {r.batch_no_snapshot: r for r in rows}
    assert set(by_batch) == {"B-1", "B-2"}
    assert Decimal(by_batch["B-1"].quantity_base) == Decimal("5")
    assert Decimal(by_batch["B-1"].unit_price_snapshot) == Decimal("90.00")
    assert Decimal(by_batch["B-1"].conversion_qty_snapshot) == Decimal("10")
    assert Decimal(by_batch["B-1"].line_amount) == Decimal("45.00")
    assert Decimal(by_batch["B-2"].quantity_base) == Decimal("5")
    assert Decimal(by_batch["B-2"].unit_price_snapshot) == Decimal("280.00")
    assert Decimal(by_batch["B-2"].line_amount) == Decimal("140.00")

    # --- Lots deducted (expired lot untouched).
    batches = {b["batch_no"]: b for b in await _batches(client, headers, product["id"])}
    assert Decimal(str(batches["B-1"]["remaining_quantity"])) == Decimal("0")
    assert Decimal(str(batches["B-2"]["remaining_quantity"])) == Decimal("5")
    assert Decimal(str(batches["OLD"]["remaining_quantity"])) == Decimal("7")
    assert batches["OLD"]["status"] == "EXPIRED"
    assert await balance_of(client, headers, product["id"]) == Decimal("12.0000")  # 5+10+7-10

    # --- Overselling beyond sellable stock is rejected (expired stock is not available).
    too_many = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{"product_id": product["id"], "uom_id": pack["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert too_many.status_code == 409, too_many.text

    # --- Return 1 pack restores 10 base to the ORIGINAL lots (B-2 then B-1).
    returned = await client.post(
        f"/api/v1/pos/sales/{data['id']}/return",
        json={
            "reason": "pack returned",
            "items": [{"sale_item_id": data["items"][0]["id"], "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert returned.status_code == 201, returned.text
    assert Decimal(returned.json()["data"]["refund_amount"]) == Decimal("185.00")

    batches = {b["batch_no"]: Decimal(str(b["remaining_quantity"])) for b in await _batches(client, headers, product["id"])}
    assert batches["B-2"] == Decimal("10")  # 5 + 5 (newest lot refilled first)
    assert batches["B-1"] == Decimal("5")  # 0 + 5
    assert batches["OLD"] == Decimal("7")  # expired lot never touched
