import asyncio
from decimal import Decimal

import pytest

from sqlalchemy import select, text

from app.modules.auth.models import User
from tests.modules.pos.helpers import make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, deactivate_then_delete


async def test_product_crud_and_price_audit(client, db_session):
    headers = await admin_headers(client)
    category = (
        await client.post("/api/v1/categories", json={"code": "GEN", "name": "General"}, headers=headers)
    ).json()["data"]

    created = await client.post(
        "/api/v1/products",
        json={
            "barcode": "012345",
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

    dup_barcode = await client.post(
        "/api/v1/products",
        json={
            "barcode": "012345",
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
    assert Decimal(patched.json()["data"]["selling_price"]) == Decimal("7.25")

    # A selling-price change adds + activates a new sale-price version
    # (spec: product_sale_prices; POS always reads the active version).
    prices = await client.get(f"/api/v1/products/{product['id']}/sale-prices", headers=headers)
    assert prices.status_code == 200, prices.text
    price_rows = prices.json()["data"]
    active = [row for row in price_rows if row["is_active"]]
    assert len(active) == 1
    assert active[0]["version"] == 2
    assert Decimal(active[0]["sale_price"]) == Decimal("7.25")

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
    assert Decimal(audit.new_values["sale_price"]) == Decimal("7.25")

    # Cannot read products without authentication.
    anon = await client.get("/api/v1/products")
    assert anon.status_code == 401

    # Cleanup
    await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")

async def test_barcode_is_operational_identifier(client):
    """Barcode-first: barcode unique+required, fast lookup."""
    headers = await admin_headers(client)
    category = (
        await client.post("/api/v1/categories", json={"code": "BAR", "name": "Barcode"}, headers=headers)
    ).json()["data"]

    # 1. Create without barcode: barcode is auto-issued.
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
    assert len(auto["barcode"]) == 6

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

    # 6. Product list search matches barcode.
    listing = await client.get(f"/api/v1/products?q={auto['barcode']}", headers=headers)
    assert listing.status_code == 200
    assert any(row["id"] == auto["id"] for row in listing.json()["data"])

    await deactivate_then_delete(client, headers, f"/api/v1/products/{auto['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


async def test_internal_barcode_sequence_collision_and_existing_barcode_preservation(
    client, db_session
):
    headers = await admin_headers(client)
    category = (
        await client.post(
            "/api/v1/categories",
            json={"code": "IBC", "name": "Internal Barcode"},
            headers=headers,
        )
    ).json()["data"]
    supplied_value = await db_session.scalar(
        text(
            """
            SELECT value
            FROM generate_series(100001, 999999) AS value
            WHERE NOT EXISTS (SELECT 1 FROM products WHERE barcode = value::text)
            ORDER BY value LIMIT 1
            """
        )
    )
    supplied = f"{supplied_value:06d}"
    first = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "barcode": supplied,
            "name": "Supplied Barcode Product",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "2.00",
        },
    )
    assert first.status_code == 201, first.text
    first_product = first.json()["data"]
    assert first_product["barcode"] == supplied

    next_value = await db_session.scalar(
        text(
            """
            SELECT value
            FROM generate_series(100001, 999999) AS value
            WHERE NOT EXISTS (SELECT 1 FROM products WHERE barcode = value::text)
            ORDER BY value LIMIT 1
            """
        )
    )
    generated = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "Collision Retry Product",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "3.00",
        },
    )
    assert generated.status_code == 201, generated.text
    generated_product = generated.json()["data"]
    assert generated_product["barcode"] == f"{next_value:06d}"

    updated = await client.patch(
        f"/api/v1/products/{first_product['id']}",
        headers=headers,
        json={"name": "Renamed Supplied Barcode Product"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["barcode"] == supplied

    found = await client.get(
        f"/api/v1/pos/products/barcode/{generated_product['barcode']}",
        headers=headers,
    )
    assert found.status_code == 200, found.text
    assert found.json()["data"]["id"] == generated_product["id"]

    await deactivate_then_delete(
        client, headers, f"/api/v1/products/{generated_product['id']}"
    )
    await deactivate_then_delete(
        client, headers, f"/api/v1/products/{first_product['id']}"
    )
    await deactivate_then_delete(
        client, headers, f"/api/v1/categories/{category['id']}"
    )


async def test_manual_six_digit_validation_and_leading_zero_pos_lookup(client):
    headers = await admin_headers(client)
    category = (
        await client.post(
            "/api/v1/categories",
            json={"code": "B6V", "name": "Six Digit Validation"},
            headers=headers,
        )
    ).json()["data"]

    invalid_values = ("12345", "1234567", "12A456")
    for value in invalid_values:
        response = await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "barcode": value,
                "name": f"Invalid {value}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
            },
        )
        assert response.status_code == 422

    created = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "barcode": "000123",
            "name": "Leading Zero Product",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()["data"]
    assert product["barcode"] == "000123"

    scanned = await client.get("/api/v1/pos/products/barcode/000123", headers=headers)
    assert scanned.status_code == 200
    assert scanned.json()["data"]["id"] == product["id"]
    manually_searched = await client.get("/api/v1/pos/products/search?q=000123", headers=headers)
    assert [row["id"] for row in manually_searched.json()["data"]] == [product["id"]]

    await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


async def test_concurrent_product_creation_allocates_unique_barcodes(client):
    headers = await admin_headers(client)
    category = (
        await client.post(
            "/api/v1/categories",
            json={"code": "B6C", "name": "Concurrent Barcodes"},
            headers=headers,
        )
    ).json()["data"]

    async def create(index: int):
        return await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": f"Concurrent Product {index}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
            },
        )

    responses = await asyncio.gather(create(1), create(2), create(3))
    assert all(response.status_code == 201 for response in responses), [r.text for r in responses]
    products = [response.json()["data"] for response in responses]
    barcodes = [product["barcode"] for product in products]
    assert len(set(barcodes)) == 3
    assert all(len(value) == 6 and value.isdigit() for value in barcodes)

    for product in products:
        await deactivate_then_delete(client, headers, f"/api/v1/products/{product['id']}")
    await deactivate_then_delete(client, headers, f"/api/v1/categories/{category['id']}")


async def test_six_digit_barcode_range_exhaustion_is_explicit(monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.exceptions import ValidationError
    from app.modules.stock.service import ProductService

    session = AsyncMock()
    session.scalar.return_value = None
    service = ProductService(session)

    with pytest.raises(ValidationError) as exc_info:
        await service._next_barcode()

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["field_errors"]["barcode"] == (
        "No internal barcodes remain from 100001 to 999999"
    )


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
