"""POS sale-price versions (spec: product_sale_prices) + Cost Price history."""

import asyncio
import httpx
import uuid
from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login


async def _make_product(client, headers, tag: str) -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"SP-{tag}", "name": f"SP Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"SP-{tag}",
            "name": f"Price Widget {tag}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "10.00",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _active(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["is_active"]]


@pytest.mark.asyncio
async def test_product_create_seeds_sale_price_version_1(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)

    prices = await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)
    assert prices.status_code == 200, prices.text
    rows = prices.json()["data"]
    assert len(rows) == 1
    assert rows[0]["version"] == 1
    assert rows[0]["is_active"] is True
    assert Decimal(rows[0]["sale_price"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_add_sale_price_creates_active_version_and_copies_selling_price(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)

    created = await client.post(
        "/api/v1/products/sale-prices",
        json={"productId": product["id"], "salePrice": "12.50", "date": "2030-01-01"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    row = created.json()["data"]
    assert row["version"] == 2
    assert row["is_active"] is True
    assert Decimal(row["selling_price"]) == Decimal("12.50")

    detail = await client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert Decimal(detail.json()["data"]["selling_price"]) == Decimal("12.50")

    prices = (await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)).json()["data"]
    assert len(_active(prices)) == 1
    assert sorted(row["version"] for row in prices) == [1, 2]
    # Newest first.
    assert prices[0]["version"] == 2


@pytest.mark.asyncio
async def test_patch_is_active_runs_activate_transaction(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await client.post(
        "/api/v1/products/sale-prices",
        json={"productId": product["id"], "salePrice": "12.50"},
        headers=headers,
    )

    # Reactivate version 1 through the generic PATCH the dialog uses.
    prices = (await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)).json()["data"]
    v1 = next(row for row in prices if row["version"] == 1)
    patched = await client.patch(
        f"/api/v1/products/sale-prices/{v1['id']}", json={"isActive": True}, headers=headers
    )
    assert patched.status_code == 200, patched.text

    prices = (await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)).json()["data"]
    assert len(_active(prices)) == 1
    assert _active(prices)[0]["version"] == 1
    detail = await client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert Decimal(detail.json()["data"]["selling_price"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_activate_rejects_other_products_row(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product_a = await _make_product(client, headers, tag)
    product_b = await _make_product(client, headers, tag + "b")

    prices_b = (await client.get(f"/api/v1/products/{product_b['id']}/sale-prices", headers=headers)).json()["data"]
    response = await client.post(
        f"/api/v1/products/{product_a['id']}/sale-prices/{prices_b[0]['id']}/activate", headers=headers
    )
    assert response.status_code == 404

    prices_a = (await client.get(f"/api/v1/products/{product_a['id']}/sale-prices", headers=headers)).json()["data"]
    ok = await client.post(
        f"/api/v1/products/{product_a['id']}/sale-prices/{prices_a[0]['id']}/activate", headers=headers
    )
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_exclusive_active_flag_under_concurrency(client):
    """Two parallel activations of different versions → exactly one winner."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    for price in ("11.00", "12.00"):
        created = await client.post(
            "/api/v1/products/sale-prices",
            json={"productId": product["id"], "salePrice": price},
            headers=headers,
        )
        assert created.status_code == 201

    prices = (await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)).json()["data"]
    v2 = next(row for row in prices if row["version"] == 2)
    v3 = next(row for row in prices if row["version"] == 3)

    from app.main import app as fastapi_app

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c1, httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c2:
        results = await asyncio.gather(
            c1.post(f"/api/v1/products/sale-prices/{v2['id']}/activate", headers=headers),
            c2.post(f"/api/v1/products/sale-prices/{v3['id']}/activate", headers=headers),
        )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]

    final = (await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)).json()["data"]
    assert len(_active(final)) == 1
    assert _active(final)[0]["id"] in {v2["id"], v3["id"]}


@pytest.mark.asyncio
async def test_cost_history_versions_and_amounts(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    pid = product["id"]

    for qty, cost in (("5", "2.00"), ("3", "3.00")):
        stock_in = await client.post(
            "/api/v1/stock/in",
            json={"paid_amount": str(Decimal(qty) * Decimal(cost)), "items": [{"product_id": pid, "quantity": qty, "unit_cost": cost}]},
            headers=headers,
        )
        assert stock_in.status_code == 201, stock_in.text

    response = await client.get(f"/api/v1/stock/products/{pid}/cost-history", headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 2
    # Newest first; versions assigned oldest → newest.
    assert [row["version"] for row in rows] == [2, 1]
    assert Decimal(rows[0]["unit_cost"]) == Decimal("3.00")
    assert Decimal(rows[0]["amount"]) == Decimal("9.00")
    assert Decimal(rows[1]["amount"]) == Decimal("10.00")
    assert rows[0]["document_no"]

    missing = await client.get(f"/api/v1/stock/products/{uuid.uuid4()}/cost-history", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_sale_price_permissions(client, db_session):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)

    await create_user_with_role(
        db_session,
        email="sp-viewer@example.com",
        password="viewerpass1",
        role_name="SP Viewer",
        permissions=["stock.view"],
    )
    await db_session.commit()
    data = await login(client, "sp-viewer@example.com", "viewerpass1")
    viewer = {"Authorization": f"Bearer {data['access_token']}"}

    # View works with stock.view.
    listing = await client.get("/api/v1/products/sale-prices", headers=viewer)
    assert listing.status_code == 200

    # Writes require product.update.
    denied = await client.post(
        "/api/v1/products/sale-prices",
        json={"productId": product["id"], "salePrice": "9.00"},
        headers=viewer,
    )
    assert denied.status_code == 403
