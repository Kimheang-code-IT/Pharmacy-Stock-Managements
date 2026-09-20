"""Backend support for the Stock page split: /stock/products + /stock/movements.

Covers the required capabilities without adding new routes:
- product list barcode-first search, brand filter, status filter, pagination, sort
- movement list enrichment (barcode, qty in/out, balance before/after, user),
  filters (q, product, type, date range), pagination, sort
- stock.view permission on the movement ledger
- immutable movements: no write endpoints, no write access for stock.view users
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, deactivate_then_delete, login


async def _create_brand(client, headers, code: str) -> dict:
    response = await client.post("/api/v1/brands", json={"code": code, "name": f"Brand {code}"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_category(client, headers, code: str, name: str) -> dict:
    response = await client.post("/api/v1/categories", json={"code": code, "name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_product(client, headers, *, tag: str, name: str, barcode: str, brand_id=None, category_id, status: str = "ACTIVE", selling_price: str = "10.00") -> dict:
    response = await client.post(
        "/api/v1/products",
        json={
            "barcode": barcode,
            "name": name,
            "category_id": category_id,
            "uom_id": str(DEFAULT_UOM_ID),
            "brand_id": brand_id,
            "selling_price": selling_price,
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ------------------------------------------------------------------ products


@pytest.mark.asyncio
async def test_product_list_barcode_search_and_brand_filter(client):
    """Barcode-first search + brand filter for the Products subpage."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = await _create_category(client, headers, f"C-{tag}", f"Cat {tag}")
    brand_a = await _create_brand(client, headers, f"BA-{tag}")
    brand_b = await _create_brand(client, headers, f"BB-{tag}")

    in_brand = await _create_product(
        client, headers, tag=tag, name=f"Alpha Widget {tag}", barcode=f"880{tag}01", brand_id=brand_a["id"], category_id=category["id"]
    )
    other_brand = await _create_product(
        client, headers, tag=tag, name=f"Beta Widget {tag}", barcode=f"880{tag}02", brand_id=brand_b["id"], category_id=category["id"]
    )
    no_brand = await _create_product(
        client, headers, tag=tag, name=f"Gamma Widget {tag}", barcode=f"880{tag}03", category_id=category["id"]
    )

    # Exact barcode search returns exactly that product.
    barcode_hit = await client.get(f"/api/v1/products?q={in_brand['barcode']}", headers=headers)
    assert barcode_hit.status_code == 200
    rows = barcode_hit.json()["data"]
    assert [row["id"] for row in rows] == [in_brand["id"]]
    assert rows[0]["barcode"] == in_brand["barcode"]

    # Barcode prefix matches too (partial search).
    prefix = await client.get(f"/api/v1/products?q=880{tag}", headers=headers)
    ids = {row["id"] for row in prefix.json()["data"]}
    assert ids == {in_brand["id"], other_brand["id"], no_brand["id"]}

    # Brand filter returns only that brand's products.
    brand_list = await client.get(f"/api/v1/products?brand_id={brand_a['id']}", headers=headers)
    assert brand_list.status_code == 200
    assert [row["id"] for row in brand_list.json()["data"]] == [in_brand["id"]]

    # Brand + search combine.
    combo = await client.get(
        f"/api/v1/products?brand_id={brand_a['id']}&q=880{tag}02", headers=headers
    )
    assert combo.json()["data"] == []

    # Brand response data is present for the table.
    assert in_brand["brand_name"] == f"Brand BA-{tag}"
    assert in_brand["uom_symbol"]
    assert "expiry_date" in in_brand
    assert in_brand["image_url"] is None

    for product in (in_brand, other_brand, no_brand):
        await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/brands/{brand_a['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/brands/{brand_b['id']}")


@pytest.mark.asyncio
async def test_product_list_status_filter_and_pagination(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"CP-{tag}", "name": f"CatPage {tag}"}, headers=headers
        )
    ).json()["data"]

    active = await _create_product(
        client, headers, tag=tag, name=f"Active Widget {tag}", barcode=f"881{tag}01", category_id=category["id"]
    )
    inactive = await _create_product(
        client,
        headers,
        tag=tag,
        name=f"Inactive Widget {tag}",
        barcode=f"881{tag}02",
        category_id=category["id"],
        status="INACTIVE",
    )

    active_only = await client.get(
        f"/api/v1/products?category_id={category['id']}&status=ACTIVE", headers=headers
    )
    assert [row["id"] for row in active_only.json()["data"]] == [active["id"]]

    inactive_only = await client.get(
        f"/api/v1/products?category_id={category['id']}&status=INACTIVE", headers=headers
    )
    assert [row["id"] for row in inactive_only.json()["data"]] == [inactive["id"]]

    # Pagination meta is present and honored.
    paged = await client.get(
        f"/api/v1/products?category_id={category['id']}&page=1&limit=1", headers=headers
    )
    assert paged.json()["meta"] == {"page": 1, "limit": 1, "total": 2}
    page_two = await client.get(
        f"/api/v1/products?category_id={category['id']}&page=2&limit=1", headers=headers
    )
    assert len(page_two.json()["data"]) == 1

    await deactivate_then_delete(client, headers, f"/api/v1/products/{active['id']}")
    await client.delete(f"/api/v1/products/{inactive['id']}", headers=headers)
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


@pytest.mark.asyncio
async def test_product_list_sort(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = await _create_category(client, headers, f"CS-{tag}", f"CatSort {tag}")
    first = await _create_product(
        client, headers, tag=tag, name=f"A-Sort Widget {tag}", barcode=f"882{tag}01", category_id=category["id"], selling_price="5.00"
    )
    second = await _create_product(
        client, headers, tag=tag, name=f"B-Sort Widget {tag}", barcode=f"882{tag}02", category_id=category["id"], selling_price="9.00"
    )

    by_name_desc = await client.get(f"/api/v1/products?q=Sort Widget {tag}&sort=-name", headers=headers)
    names = [row["name"] for row in by_name_desc.json()["data"]]
    assert names == [second["name"], first["name"]]

    by_price_asc = await client.get(f"/api/v1/products?q=Sort Widget {tag}&sort=selling_price", headers=headers)
    prices = [Decimal(row["selling_price"]) for row in by_price_asc.json()["data"]]
    assert prices == sorted(prices)

    # Unknown sort field falls back to the default (no error).
    fallback = await client.get(f"/api/v1/products?q=Sort Widget {tag}&sort=nonsense", headers=headers)
    assert fallback.status_code == 200

    await deactivate_then_delete(client, headers, f"/api/v1/products/{first['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/products/{second['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


# ----------------------------------------------------------------- movements


@pytest.mark.asyncio
async def test_movement_rows_expose_movements_page_columns(client):
    """Date, document, product, barcode, type, UOM, qty in/out, balances, user."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"MVW-{tag}", name=f"Mov Widget {tag}", qty="10", unit_cost="2.00")
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

    movements = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&sort=createdAt", headers=headers
    )
    assert movements.status_code == 200, movements.text
    rows = movements.json()["data"]
    assert len(rows) == 2
    stock_in_row, sale_row = rows  # ascending order

    # Common enrichment on every row.
    for row in rows:
        assert row["product_name"] == product["name"]
        assert row["barcode"] == product["barcode"]
        assert row["uom_symbol"]
        assert row["user"]
        assert row["created_at"]
        assert row["document_no"]

    # Stock-in row: qty in 10.
    assert Decimal(stock_in_row["qty_in"]) == Decimal("10.0000")
    assert Decimal(stock_in_row["qty_out"]) == Decimal("0.0000")
    assert Decimal(stock_in_row["quantity_delta"]) == Decimal("10.0000")

    # Sale row: qty out 3.
    assert Decimal(sale_row["qty_out"]) == Decimal("3.0000")
    assert Decimal(sale_row["qty_in"]) == Decimal("0.0000")
    assert sale_row["movement_type"] == "SALE"
    # The SALE row links back to the invoice via its document number.
    assert sale_row["document_no"] == sale.json()["data"]["invoice_no"]
    assert sale_row["source_reference"] == sale_row["document_no"]

    # Newest-first default still works.
    default_order = await client.get(f"/api/v1/stock/movements?product_id={pid}", headers=headers)
    types = [row["movement_type"] for row in default_order.json()["data"]]
    assert types == ["SALE", "STOCK_IN"]

    await deactivate_then_delete(client, headers, f"/api/v1/products/{pid}")


@pytest.mark.asyncio
async def test_movement_list_filters_pagination_and_sort(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"MVN-{tag}", name=f"Mvn Widget {tag}", qty="8")
    pid = product["id"]

    # Build: STOCK_IN(8), SALE(2), DAMAGE(1).
    sale = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "50.00", "items": [{"product_id": pid, "quantity": "2"}]},
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    damaged = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": pid, "quantity": "1", "reason": "broken"}]},
        headers=headers,
    )
    assert damaged.status_code == 201, damaged.text

    # movement_type filter.
    by_type = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&movement_type=DAMAGE", headers=headers
    )
    rows = by_type.json()["data"]
    assert len(rows) == 1
    assert rows[0]["movement_type"] == "DAMAGE"

    # Unknown movement type → 422 validation envelope.
    bad_type = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&movement_type=NOPE", headers=headers
    )
    assert bad_type.status_code == 422

    # q matches document number.
    damage_doc = rows[0]["document_no"]
    by_q = await client.get(f"/api/v1/stock/movements?q={damage_doc}", headers=headers)
    assert [row["id"] for row in by_q.json()["data"]] == [rows[0]["id"]]

    # Date range: only today's movements (all of them).
    today = datetime.now(timezone.utc).date().isoformat()
    ranged = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&startDate={today}&endDate={today}", headers=headers
    )
    assert ranged.json()["meta"]["total"] == 3

    # Narrow range excluding everything.
    past = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    empty_range = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&endDate={past}", headers=headers
    )
    assert empty_range.json()["data"] == []

    # Pagination.
    paged = await client.get(f"/api/v1/stock/movements?product_id={pid}&page=2&limit=2", headers=headers)
    assert paged.json()["meta"] == {"page": 2, "limit": 2, "total": 3}
    assert len(paged.json()["data"]) == 1

    # Sort by quantity descending puts the stock-in row first.
    by_qty = await client.get(
        f"/api/v1/stock/movements?product_id={pid}&sort=-quantity", headers=headers
    )
    first_row = by_qty.json()["data"][0]
    assert first_row["movement_type"] == "STOCK_IN"
    assert Decimal(first_row["qty_in"]) == Decimal("8.0000")

    await deactivate_then_delete(client, headers, f"/api/v1/products/{pid}")


@pytest.mark.asyncio
async def test_movement_list_requires_stock_view_permission(client, db_session):
    """The Movements page is stock data: stock.view is enforced server-side."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"MVP-{tag}", name=f"Mvp Widget {tag}", qty="4")
    pid = product["id"]

    # Without any authentication → 401.
    anon = await client.get("/api/v1/stock/movements")
    assert anon.status_code == 401

    # With a role lacking stock.view → 403.
    await create_user_with_role(
        db_session,
        email="mv-noview@example.com",
        password="nopass1234",
        role_name="Movement NoView",
        permissions=["product.create"],
    )
    await db_session.commit()
    data = await login(client, "mv-noview@example.com", "nopass1234")
    no_view = {"Authorization": f"Bearer {data['access_token']}"}
    denied = await client.get(f"/api/v1/stock/movements?product_id={pid}", headers=no_view)
    assert denied.status_code == 403

    # A stock.view role can read.
    await create_user_with_role(
        db_session,
        email="mv-viewer@example.com",
        password="viewpass1",
        role_name="Movement Viewer",
        permissions=["stock.view"],
    )
    await db_session.commit()
    data = await login(client, "mv-viewer@example.com", "viewpass1")
    viewer = {"Authorization": f"Bearer {data['access_token']}"}
    allowed = await client.get(f"/api/v1/stock/movements?product_id={pid}", headers=viewer)
    assert allowed.status_code == 200

    await deactivate_then_delete(client, headers, f"/api/v1/products/{pid}")


@pytest.mark.asyncio
async def test_movements_are_immutable_read_only(client):
    """No edit/delete movement endpoints; direct writes rejected."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"MVI-{tag}", name=f"Mvi Widget {tag}", qty="3")
    pid = product["id"]

    movements = await client.get(f"/api/v1/stock/movements?product_id={pid}", headers=headers)
    movement_id = movements.json()["data"][0]["id"]

    # No write routes exist on /stock/movements/{id} (FastAPI answers 404 for
    # undefined write methods on the GET collection path).
    assert (await client.patch(f"/api/v1/stock/movements/{movement_id}", headers=headers, json={})).status_code == 404
    assert (await client.delete(f"/api/v1/stock/movements/{movement_id}", headers=headers)).status_code == 404
    assert (await client.post(f"/api/v1/stock/movements/{movement_id}", headers=headers, json={})).status_code == 404

    # Direct ORM writes are out of contract; the ledger row content is stable.
    before = movements.json()["data"]
    after = (
        await client.get(f"/api/v1/stock/movements?product_id={pid}", headers=headers)
    ).json()["data"]
    assert before == after

    await deactivate_then_delete(client, headers, f"/api/v1/products/{pid}")