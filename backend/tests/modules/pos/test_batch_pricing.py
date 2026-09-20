"""Batch-based POS pricing end-to-end (spec: batch pricing → FEFO → checkout).

Covers: catalog shows the FEFO lot price and sellable stock, per-batch blended
checkout, snapshots survive later price edits, inactive/expired lots never
allocated, missing price blocks the sale, returns restore the original lot and
concurrent checkouts cannot oversell.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_product(client, headers, tag: str, *, selling_price="14.00") -> dict:
    # "ZZ" prefix keeps these fixtures at the END of the shared test database's
    # name-ordered product list so pagination-based tests are unaffected.
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"ZZBP-{tag}", "name": f"ZZBP Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"ZZBP-{tag}",
            "name": f"ZZ Batch Widget {tag}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": selling_price,
            "track_batch": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _stock_in(client, headers, product_id, *, qty, unit_cost, batch_no, expiry) -> None:
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


async def _set_batch_price(client, headers, product_id, *, batch_no, sale_price) -> None:
    response = await client.post(
        "/api/v1/products/sale-prices",
        json={
            "productId": product_id,
            "salePrice": sale_price,
            "batchNo": batch_no,
            "uomPrices": [
                {
                    "uomId": str(DEFAULT_UOM_ID),
                    "factorToBase": 1,
                    "salePrice": sale_price,
                    "isDefaultSale": True,
                }
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


async def _sale(client, headers, items, **extra):
    return await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000000.00",
            "items": items,
            **extra,
        },
        headers=headers,
    )


async def _batches(client, headers, product_id) -> list[dict]:
    response = await client.get(
        f"/api/v1/stock/products/{product_id}/batches", params={"status": "All"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_case1_single_batch_pos_price(client):
    """CASE 1: one batch, stock 10, price $10 → POS shows $10 / stock 10."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="2.00", batch_no="B-1", expiry="2030-01-01")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="10.00")

    card = await _catalog(client, headers, product["name"])
    assert Decimal(str(card["selling_price"])) == Decimal("10.00")
    assert Decimal(str(card["sellable_stock"])) == Decimal("10")
    assert card["next_batch_no"] == "B-1"
    assert card["price_configured"] is True

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "3"}])
    assert sale.status_code == 201, sale.text
    assert Decimal(sale.json()["data"]["subtotal"]) == Decimal("30.00")


@pytest.mark.asyncio
async def test_case2_two_batches_show_fefo_price(client):
    """CASE 2: B1 stock5 $10 expires first, B2 stock10 $30 → POS shows $10/15."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="6.00", batch_no="B-1", expiry="2026-10-03")
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-2", expiry="2026-10-09")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="10.00")
    await _set_batch_price(client, headers, product["id"], batch_no="B-2", sale_price="30.00")

    card = await _catalog(client, headers, product["name"])
    assert card["next_batch_no"] == "B-1"
    assert Decimal(str(card["selling_price"])) == Decimal("10.00")
    assert Decimal(str(card["sellable_stock"])) == Decimal("15")


@pytest.mark.asyncio
async def test_case3_qty_spans_batches_blends_price(client, db_session):
    """CASE 3: buy 7 → 5×$10 + 2×$30 = $110, per-batch snapshots."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="6.00", batch_no="B-1", expiry="2026-10-03")
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-2", expiry="2026-10-09")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="10.00")
    await _set_batch_price(client, headers, product["id"], batch_no="B-2", sale_price="30.00")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "7"}])
    assert sale.status_code == 201, sale.text
    data = sale.json()["data"]
    assert Decimal(data["subtotal"]) == Decimal("110.00")
    assert Decimal(data["grand_total"]) == Decimal("110.00")

    detail = (await client.get(f"/api/v1/pos/sales/{data['id']}", headers=headers)).json()["data"]
    line = detail["items"][0]
    # Blended display price: 110 / 7 = 15.71.
    assert Decimal(line["unit_price"]) == Decimal("15.71")

    # Per-lot snapshots: 5 @ 10 + 2 @ 30.
    from sqlalchemy import select

    from app.modules.pos.models import SaleItemBatch

    rows = (
        await db_session.execute(
            select(SaleItemBatch).where(SaleItemBatch.sale_item_id == uuid.UUID(line["id"]))
        )
    ).scalars().all()
    by_batch = {row.batch_no_snapshot: row for row in rows}
    assert Decimal(by_batch["B-1"].unit_price_snapshot) == Decimal("10.00")
    assert Decimal(by_batch["B-2"].unit_price_snapshot) == Decimal("30.00")
    assert Decimal(by_batch["B-1"].quantity_base) == Decimal("5")
    assert Decimal(by_batch["B-2"].quantity_base) == Decimal("2")
    assert sum((Decimal(r.line_amount) for r in rows), Decimal("0")) == Decimal("110.00")


@pytest.mark.asyncio
async def test_case4_depleted_first_batch_next_price(client):
    """CASE 4: once B1 is empty, POS next price is B2 = $30."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="6.00", batch_no="B-1", expiry="2026-10-03")
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-2", expiry="2026-10-09")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="10.00")
    await _set_batch_price(client, headers, product["id"], batch_no="B-2", sale_price="30.00")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "5"}])
    assert sale.status_code == 201, sale.text

    card = await _catalog(client, headers, product["name"])
    assert card["next_batch_no"] == "B-2"
    assert Decimal(str(card["selling_price"])) == Decimal("30.00")
    assert Decimal(str(card["sellable_stock"])) == Decimal("10")


@pytest.mark.asyncio
async def test_case5_expired_batch_not_allocated(client):
    """CASE 5: an expired lot with stock is never sold or counted as sellable."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="1.00", batch_no="OLD", expiry="2020-01-01")
    await _stock_in(client, headers, product["id"], qty="4", unit_cost="20.00", batch_no="NEW", expiry="2030-01-01")
    await _set_batch_price(client, headers, product["id"], batch_no="OLD", sale_price="1.00")
    await _set_batch_price(client, headers, product["id"], batch_no="NEW", sale_price="30.00")

    card = await _catalog(client, headers, product["name"])
    assert card["next_batch_no"] == "NEW"
    assert Decimal(str(card["sellable_stock"])) == Decimal("4")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "4"}])
    assert sale.status_code == 201, sale.text
    assert Decimal(sale.json()["data"]["subtotal"]) == Decimal("120.00")


@pytest.mark.asyncio
async def test_case6_inactive_batch_not_allocated(client):
    """CASE 6: an inactive lot with stock is never allocated to a sale."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="1.00", batch_no="OFF", expiry="2030-01-01")
    await _stock_in(client, headers, product["id"], qty="4", unit_cost="20.00", batch_no="ON", expiry="2030-06-01")
    await _set_batch_price(client, headers, product["id"], batch_no="OFF", sale_price="1.00")
    await _set_batch_price(client, headers, product["id"], batch_no="ON", sale_price="30.00")

    batches = await _batches(client, headers, product["id"])
    off = next(row for row in batches if row["batch_no"] == "OFF")
    toggled = await client.patch(
        f"/api/v1/stock/products/{product['id']}/batches/{off['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["data"]["is_active"] is False

    card = await _catalog(client, headers, product["name"])
    assert card["next_batch_no"] == "ON"
    assert Decimal(str(card["sellable_stock"])) == Decimal("4")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "4"}])
    assert sale.status_code == 201, sale.text
    assert Decimal(sale.json()["data"]["subtotal"]) == Decimal("120.00")


@pytest.mark.asyncio
async def test_case7_missing_price_blocks_sale(client):
    """CASE 7: stock but no configured price → price_configured false / blocked."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag, selling_price="0.00")
    await _stock_in(client, headers, product["id"], qty="3", unit_cost="2.00", batch_no="NP", expiry="2030-01-01")

    card = await _catalog(client, headers, product["name"])
    assert card["price_configured"] is False

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "1"}])
    assert sale.status_code == 422, sale.text


@pytest.mark.asyncio
async def test_case8_price_edit_does_not_change_history(client):
    """CASE 8: changing a batch price later leaves the completed sale unchanged."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-1", expiry="2030-01-01")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="30.00")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "2"}])
    assert sale.status_code == 201, sale.text
    sale_id = sale.json()["data"]["id"]
    assert Decimal(sale.json()["data"]["subtotal"]) == Decimal("60.00")

    # Reprice the same lot, then re-read the sale: snapshot must be untouched.
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="35.00")
    after = (await client.get(f"/api/v1/pos/sales/{sale_id}", headers=headers)).json()["data"]
    assert Decimal(after["subtotal"]) == Decimal("60.00")
    assert Decimal(after["items"][0]["unit_price"]) == Decimal("30.00")


@pytest.mark.asyncio
async def test_case9_return_restores_original_batch(client):
    """CASE 9: a return restores stock to the batch the line was sold from."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="6.00", batch_no="B-1", expiry="2026-10-03")
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="20.00", batch_no="B-2", expiry="2026-10-09")
    await _set_batch_price(client, headers, product["id"], batch_no="B-1", sale_price="10.00")
    await _set_batch_price(client, headers, product["id"], batch_no="B-2", sale_price="30.00")

    sale = await _sale(client, headers, [{"product_id": product["id"], "quantity": "7"}])
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    line_id = sale_data["items"][0]["id"]

    returned = await client.post(
        f"/api/v1/pos/sales/{sale_data['id']}/return",
        json={"reason": "customer changed mind", "items": [{"sale_item_id": line_id, "quantity": "2"}]},
        headers=headers,
    )
    assert returned.status_code == 201, returned.text

    batches = {row["batch_no"]: Decimal(str(row["remaining_quantity"])) for row in await _batches(client, headers, product["id"])}
    # B1 fully consumed (0), B2 sold 2 of 10 → 8, then returned 2 (newest-first) → 10.
    assert batches["B-1"] == Decimal("0")
    assert batches["B-2"] == Decimal("10")


@pytest.mark.asyncio
async def test_case10_concurrent_batch_sales_cannot_oversell(client):
    """CASE 10: two checkouts racing the last batch unit: exactly one wins."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="1", unit_cost="2.00", batch_no="LAST", expiry="2030-01-01")
    await _set_batch_price(client, headers, product["id"], batch_no="LAST", sale_price="10.00")

    async def sell():
        return await _sale(client, headers, [{"product_id": product["id"], "quantity": "1"}])

    first, second = await asyncio.gather(sell(), sell())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409], (first.text, second.text)
