import pytest

from sqlalchemy import select

from app.modules.auth.models import User
from tests.utils import DEFAULT_UOM_ID, admin_headers


async def test_product_crud_sku_conflict_and_price_audit(client, db_session):
    headers = await admin_headers(client)
    category = (
        await client.post("/api/v1/categories", json={"code": "GEN", "name": "General"}, headers=headers)
    ).json()["data"]

    created = await client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-0001",
            "barcode": "1234567890",
            "name": "Coffee 500g",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "cost_price": "4.00",
            "selling_price": "6.50",
            "minimum_stock": "5",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product = created.json()["data"]
    assert float(product["quantity"]) == 0.0
    assert product["category_name"] == "General"

    dup_sku = await client.post(
        "/api/v1/products",
        json={"sku": "SKU-0001", "name": "Dup", "category_id": category["id"], "uom_id": str(DEFAULT_UOM_ID), "selling_price": "1"},
        headers=headers,
    )
    assert dup_sku.status_code == 409

    dup_barcode = await client.post(
        "/api/v1/products",
        json={
            "sku": "SKU-0002",
            "barcode": "1234567890",
            "name": "Dup",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "1",
        },
        headers=headers,
    )
    assert dup_barcode.status_code == 409

    patched = await client.patch(
        f"/api/v1/products/{product['id']}", json={"selling_price": "7.25"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["selling_price"] == "7.25"

    # A selling-price change adds + activates a new sale-price version
    # (spec: product_sale_prices; POS always reads the active version).
    prices = await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)
    assert prices.status_code == 200, prices.text
    price_rows = prices.json()["data"]
    active = [row for row in price_rows if row["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == 2
    assert active[0]["sale_price"] == "7.25"

    # Price change must be audited.
    result = await db_session.execute(
        select(User).where(User.email == "admin@gmail.com")
    )
    admin = result.scalar_one()
    from app.shared.audit.models import AuditLog

    audit = await db_session.scalar(
        select(AuditLog)
        .where(AuditLog.action == "sale_price_added", AuditLog.entity_id == active[0]["id"])
        .order_by(AuditLog.created_at.desc())
    )
    assert audit is not None
    assert audit.user_id == admin.id
    assert audit.new_values["sale_price"] == "7.25"

    # Cannot read products without authentication.
    anon = await client.get("/api/v1/products")
    assert anon.status_code == 401

    # Cleanup
    await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    await client.delete(f"/api/v1/categories/{category['id']}", headers=headers)
