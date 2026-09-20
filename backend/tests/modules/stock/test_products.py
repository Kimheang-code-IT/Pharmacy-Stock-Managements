import pytest

from sqlalchemy import select

from app.modules.auth.models import User
from tests.modules.pos.helpers import make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, deactivate_then_delete


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
    await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")

async def test_barcode_is_operational_identifier(client):
    """Barcode-first: sku optional, barcode unique+required, fast lookup."""
    headers = await admin_headers(client)
    category = (
        await client.post("/api/v1/categories", json={"code": "BAR", "name": "Barcode"}, headers=headers)
    ).json()["data"]

    # 1. Create without sku and without barcode: barcode is auto-issued.
    no_ids = await client.post(
        "/api/v1/products",
        json={
            "name": "Auto Barcode Product",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "2.00",
        },
        headers=headers,
    )
    assert no_ids.status_code == 201, no_ids.text
    auto = no_ids.json()["data"]
    assert auto["barcode"]
    assert auto["barcode"].isdigit()
    assert len(auto["barcode"]) == 13
    assert auto["sku"] is None

    # 2. Barcode lookup returns the product (POS operational path).
    found = await client.get(f"/api/v1/pos/products/barcode/{auto['barcode']}", headers=headers)
    assert found.status_code == 200, found.text
    assert found.json()["data"]["id"] == auto["id"]

    # 3. Unknown barcode -> 404.
    missing = await client.get("/api/v1/pos/products/barcode/nope-nope", headers=headers)
    assert missing.status_code == 404

    # 4. Duplicate barcode rejected.
    dup = await client.post(
        "/api/v1/products",
        json={
            "barcode": auto["barcode"],
            "name": "Dup Barcode",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "1.00",
        },
        headers=headers,
    )
    assert dup.status_code == 409

    # 5. POS search by exact barcode short-circuits to the product.
    searched = await client.get(
        f"/api/v1/pos/products/search?q={auto['barcode']}", headers=headers
    )
    assert searched.status_code == 200, searched.text
    results = searched.json()["data"]
    assert [row["id"] for row in results] == [auto["id"]]

    # 6. sku can be added later and stays unique.
    patched = await client.patch(
        f"/api/v1/products/{auto['id']}", json={"sku": "LEGACY-1"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["sku"] == "LEGACY-1"

    # 7. Product list search matches barcode.
    listing = await client.get(f"/api/v1/products?q={auto['barcode']}", headers=headers)
    assert listing.status_code == 200
    assert any(row["id"] == auto["id"] for row in listing.json()["data"])

    await deactivate_then_delete(client, headers, f"/api/v1/products/{auto['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


async def test_product_delete_with_sale_history_keeps_history(client, db_session):
    """An inactive product can be hard-deleted; the sale keeps its snapshots."""
    headers = await admin_headers(client)
    product = await make_stocked_product(
        client, headers, sku="PRDH-1", name="Product History Widget", qty="10"
    )

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    # Active products still cannot be deleted.
    blocked = await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    assert blocked.status_code == 409

    deactivated = await client.patch(
        f"/api/v1/products/{product['id']}", json={"status": "INACTIVE"}, headers=headers
    )
    assert deactivated.status_code == 200

    deleted = await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(f"/api/v1/products/{product['id']}", headers=headers)).status_code == 404

    # The sale line keeps its product-name snapshot and loses the live link.
    from app.modules.pos.models import SaleItem

    sale_item = await db_session.scalar(
        select(SaleItem).where(SaleItem.product_name == "Product History Widget")
    )
    assert sale_item is not None
    assert sale_item.product_id is None


async def test_product_delete_with_stock_in_history_keeps_history(client, db_session):
    """A product with stock-in history can be deleted; the purchase keeps its name."""
    headers = await admin_headers(client)
    product = await make_stocked_product(
        client, headers, sku="PRDS-1", name="Product Stock Widget", qty="3"
    )

    deactivated = await client.patch(
        f"/api/v1/products/{product['id']}", json={"status": "INACTIVE"}, headers=headers
    )
    assert deactivated.status_code == 200

    deleted = await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert (await client.get(f"/api/v1/products/{product['id']}", headers=headers)).status_code == 404

    from app.modules.stock.models import StockTransactionItem

    item = await db_session.scalar(
        select(StockTransactionItem).where(StockTransactionItem.product_name == "Product Stock Widget")
    )
    assert item is not None
    assert item.product_id is None


async def test_product_default_supplier_stored_shown_and_cleared(client):
    """A product keeps an optional default supplier (fast-purchase prefill)."""
    headers = await admin_headers(client)
    category = (
        await client.post("/api/v1/categories", json={"code": "SUP", "name": "Supplier"}, headers=headers)
    ).json()["data"]
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"name": "Default Vendor", "phone": "012345678"},
            headers=headers,
        )
    ).json()["data"]

    created = await client.post(
        "/api/v1/products",
        json={
            "name": "Supplier Product",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "3.00",
            "supplier_id": supplier["id"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product = created.json()["data"]
    assert product["supplier_id"] == supplier["id"]
    assert product["supplier_name"] == "Default Vendor"

    # Detail read keeps the supplier.
    detail = await client.get(f"/api/v1/products/{product['id']}", headers=headers)
    assert detail.json()["data"]["supplier_id"] == supplier["id"]

    # Explicit null clears the default supplier.
    cleared = await client.patch(
        f"/api/v1/products/{product['id']}", json={"supplier_id": None}, headers=headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["supplier_id"] is None

    # Unknown supplier is rejected.
    unknown = await client.patch(
        f"/api/v1/products/{product['id']}",
        json={"supplier_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert unknown.status_code == 404

    await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")
