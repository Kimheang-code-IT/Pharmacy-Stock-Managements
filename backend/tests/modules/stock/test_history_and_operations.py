"""History-dialog kind filters + GET/POST /stock/operations read model."""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_stocked_product
from tests.utils import admin_headers


@pytest.mark.asyncio
async def test_damage_dialog_excludes_expire(client):
    """Expiry is a separate operation and never folds into the Damage dialog."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"EXPD-{tag}", name=f"Expiry Widget {tag}", qty="10")
    pid = product["id"]
    tracked = await client.patch(f"/api/v1/products/{pid}", json={"expiry_tracking": True}, headers=headers)
    assert tracked.status_code == 200, tracked.text

    damaged = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": pid, "quantity": "1", "reason": "dropped"}]},
        headers=headers,
    )
    assert damaged.status_code == 201, damaged.text
    expired = await client.post(
        "/api/v1/stock/expire",
        json={"items": [{"product_id": pid, "quantity": "1", "expiry_date": "2026-01-01", "note": "old"}]},
        headers=headers,
    )
    assert expired.status_code == 201, expired.text

    damage = await client.get(f"/api/v1/stock/products/{pid}/history?type=damage", headers=headers)
    rows = damage.json()["data"]
    assert len(rows) == 1
    assert rows[0]["type"] == "Damage"
    assert rows[0]["note"] == "dropped"

    # Full history still contains the EXPIRE row (admin/debug view).
    everything = await client.get(f"/api/v1/stock/products/{pid}/history?type=all", headers=headers)
    types = {row["type"] for row in everything.json()["data"]}
    assert "Expire" in types


@pytest.mark.asyncio
async def test_history_kind_rows_and_display_labels(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"KIND-{tag}", name=f"Kind Widget {tag}", qty="6")
    pid = product["id"]

    sale = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "100.00", "items": [{"product_id": pid, "quantity": "2"}]},
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    sale_return = await client.post(
        f"/api/v1/pos/sales/{sale.json()['data']['id']}/return",
        json={"reason": "wrong color", "items": [{"sale_item_id": sale.json()["data"]["items"][0]["id"], "quantity": "1", "restock": True}]},
        headers=headers,
    )
    assert sale_return.status_code == 201, sale_return.text

    stock_in = await client.get(f"/api/v1/stock/products/{pid}/history?type=stock_in", headers=headers)
    in_rows = stock_in.json()["data"]
    kinds = {row["kind"] for row in in_rows}
    types = {row["type"] for row in in_rows}
    assert kinds == {"stock_in"}
    assert types == {"Stock In", "Sale Return"}

    stock_out = await client.get(f"/api/v1/stock/products/{pid}/history?type=stock_out", headers=headers)
    out_rows = stock_out.json()["data"]
    assert {row["type"] for row in out_rows} == {"Sale"}
    assert all(Decimal(row["qty"]) < 0 for row in out_rows)


@pytest.mark.asyncio
async def test_stock_operations_list_and_quick_create(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"OPS-{tag}", name=f"Ops Widget {tag}", qty="10")

    # Quick stock-in through the generic operations endpoint.
    created = await client.post(
        "/api/v1/stock/operations",
        json={
            "type": "stock_in",
            "productId": product["id"],
            "quantity": 4,
            "unitCost": "2.50",
            "note": "quick op",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    record = created.json()["data"]
    assert record["reference"]
    assert record["product"] == product["name"]

    listing = await client.get("/api/v1/stock/operations", headers=headers)
    assert listing.status_code == 200, listing.text
    docs = listing.json()["data"]
    doc = next(d for d in docs if d["id"] == record["id"])
    assert doc["purchase_no"] if "purchase_no" in doc else doc["purchaseNo"]
    assert doc["items"]
    item = doc["items"][0]
    assert item["productId"] == product["id"]
    assert Decimal(item["price"]) == Decimal("2.50")
    assert Decimal(item["quantity"]) == Decimal("4.0000")
    assert Decimal(doc["total"]) == Decimal("10.00")

    # The cost-price dialog source of truth: productId/price/quantity per item.
    assert item["name"] == product["name"]
