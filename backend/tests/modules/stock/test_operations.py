import asyncio
from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_product(client, headers, *, sku: str, name: str, expiry_tracking: bool = False):
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
                "selling_price": "10.00",
                "expiry_tracking": expiry_tracking,
            },
            headers=headers,
        )
    ).json()["data"]
    return product


async def _balance(client, headers, product_id) -> dict:
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    data = response.json()["data"]
    return {"quantity": Decimal(data["quantity"]), "average_cost": Decimal(data["average_cost"])}


async def test_stock_in_weighted_average_and_movements(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="SI-1", name="Stock In Widget")

    first = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "20.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    doc1 = first.json()["data"]
    assert doc1["document_no"].startswith("STI-")
    assert doc1["total_amount"] == "20.00"
    assert doc1["items"][0]["product_name"] == "Stock In Widget"

    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("10.0000")
    assert balance["average_cost"] == Decimal("2.00")

    second = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "40.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "4.00"}],
        },
        headers=headers,
    )
    assert second.status_code == 201
    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("20.0000")
    assert balance["average_cost"] == Decimal("3.00"), "weighted average cost must update"

    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}", headers=headers
    )
    assert movements.status_code == 200
    assert movements.json()["meta"]["total"] == 2
    assert all(m["movement_type"] == "STOCK_IN" for m in movements.json()["data"])

    history = await client.get(f"/api/v1/stock/products/{product['id']}/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["meta"]["total"] == 2


async def test_stock_in_supplier_debt_partial_and_full(client):
    headers = await admin_headers(client)
    supplier = (
        await client.post("/api/v1/suppliers", json={"name": "Debt Supplier"}, headers=headers)
    ).json()["data"]
    product = await _make_product(client, headers, sku="SI-2", name="Debt Widget")

    partial = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "5.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    assert partial.status_code == 201, partial.text
    data = partial.json()["data"]
    assert data["debt_created"] is True
    assert data["paid_amount"] == "5.00"

    debts = await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)
    assert debts.status_code == 200
    debt = debts.json()["data"][0]
    assert debt["original_amount"] == "10.00"
    assert debt["paid_amount"] == "5.00"
    assert debt["remaining_amount"] == "5.00"
    assert debt["status"] == "PARTIAL"
    assert debt["document_no"] == data["document_no"]

    history = await client.get(
        f"/api/v1/suppliers/{supplier['id']}/history", headers=headers
    )
    assert history.status_code == 200
    assert history.json()["meta"]["total"] == 1
    assert history.json()["data"][0]["document_no"] == data["document_no"]

    full = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "4.00",
            "items": [{"product_id": product["id"], "quantity": "4", "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    assert full.status_code == 201
    assert full.json()["data"]["debt_created"] is False


async def test_stock_in_requires_full_payment_without_supplier(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="SI-3", name="Cash Widget")
    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "0",
            "items": [{"product_id": product["id"], "quantity": "5", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


async def test_adjustment_in_out_and_audit(client, db_session):
    from sqlalchemy import select

    from app.shared.audit.models import AuditLog

    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="ADJ-1", name="Adjust Widget")

    await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "10.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "1.00"}],
        },
        headers=headers,
    )

    counted = await client.post(
        "/api/v1/stock/adjust",
        json={
            "items": [
                {
                    "product_id": product["id"],
                    "actual_quantity": "12",
                    "reason": "Recount found extra units",
                }
            ]
        },
        headers=headers,
    )
    assert counted.status_code == 201, counted.text
    item = counted.json()["data"]["items"][0]
    assert Decimal(item["system_quantity"]) == Decimal("10")
    assert Decimal(item["actual_quantity"]) == Decimal("12")
    assert Decimal(item["quantity"]) == Decimal("2")

    counted_out = await client.post(
        "/api/v1/stock/adjust",
        json={
            "items": [
                {
                    "product_id": product["id"],
                    "system_quantity": "12",
                    "actual_quantity": "9",
                    "reason": "Shrinkage",
                }
            ]
        },
        headers=headers,
    )
    assert counted_out.status_code == 201
    assert Decimal(counted_out.json()["data"]["items"][0]["quantity"]) == Decimal("-3")

    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("9.0000")

    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "stock_adjustment").order_by(AuditLog.created_at.desc())
    )
    assert audit is not None

    missing_reason = await client.post(
        "/api/v1/stock/adjust",
        json={"items": [{"product_id": product["id"], "actual_quantity": "9"}]},
        headers=headers,
    )
    assert missing_reason.status_code == 422


async def test_damage_and_expire_rules(client, db_session):
    from sqlalchemy import select

    from app.shared.audit.models import AuditLog

    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="DMG-1", name="Damage Widget")
    tracked = await _make_product(client, headers, sku="EXP-1", name="Expiry Widget", expiry_tracking=True)

    await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "26.00",
            "items": [
                {"product_id": product["id"], "quantity": "10", "unit_cost": "1.00"},
                {"product_id": tracked["id"], "quantity": "8", "unit_cost": "2.00", "batch_no": "B1"},
            ],
        },
        headers=headers,
    )

    damaged = await client.post(
        "/api/v1/stock/damage",
        json={
            "items": [
                {"product_id": product["id"], "quantity": "2", "reason": "Broken on shelf"}
            ]
        },
        headers=headers,
    )
    assert damaged.status_code == 201, damaged.text
    doc = damaged.json()["data"]
    assert doc["document_no"].startswith("DMG-")
    assert Decimal(doc["total_amount"]) == Decimal("2.00")

    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("8.0000")

    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "stock_damage").order_by(AuditLog.created_at.desc())
    )
    assert audit is not None

    expired = await client.post(
        "/api/v1/stock/expire",
        json={
            "items": [
                {
                    "product_id": tracked["id"],
                    "quantity": "3",
                    "batch_no": "B1",
                    "expiry_date": "2026-01-01",
                    "note": "Expired batch",
                }
            ]
        },
        headers=headers,
    )
    assert expired.status_code == 201, expired.text
    assert expired.json()["data"]["document_no"].startswith("EXP-")
    balance = await _balance(client, headers, tracked["id"])
    assert balance["quantity"] == Decimal("5.0000")

    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "stock_expire").order_by(AuditLog.created_at.desc())
    )
    assert audit is not None

    # Expiry on a product without expiry tracking is rejected.
    no_track = await client.post(
        "/api/v1/stock/expire",
        json={"items": [{"product_id": product["id"], "quantity": "1"}]},
        headers=headers,
    )
    assert no_track.status_code == 422

    # Damage without a reason is rejected.
    no_reason = await client.post(
        "/api/v1/stock/damage", json={"items": [{"product_id": product["id"], "quantity": "1"}]},
        headers=headers,
    )
    assert no_reason.status_code == 422


async def test_oversell_rejected_unless_setting_allows(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="NEG-1", name="Negative Widget")

    # Start from a neutral state regardless of other suites.
    await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"pos": {"allow_negative_stock": False}}},
        headers=headers,
    )

    rejected = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": product["id"], "quantity": "5", "reason": "beyond stock"}]},
        headers=headers,
    )
    assert rejected.status_code == 409
    assert "Insufficient stock" in rejected.json()["detail"]["message"]

    # Enable allow_negative_stock and retry.
    settings = await client.get("/api/v1/admin/settings", headers=headers)
    patched = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"pos": {"allow_negative_stock": True}}},
        headers=headers,
    )
    assert patched.status_code == 200

    allowed = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": product["id"], "quantity": "5", "reason": "allowed negative"}]},
        headers=headers,
    )
    assert allowed.status_code == 201, allowed.text
    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("-5.0000")

    # Restore the setting.
    await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"pos": {"allow_negative_stock": False}}},
        headers=headers,
    )


async def test_stock_in_rollback_on_failure(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="RB-1", name="Rollback Widget")

    # No supplier + partial payment fails AFTER movements were staged: everything
    # must roll back (balance unchanged, no movements persisted).
    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "1.00",
            "items": [{"product_id": product["id"], "quantity": "7", "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    assert response.status_code == 422

    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("0.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}", headers=headers
    )
    assert movements.json()["meta"]["total"] == 0


async def test_concurrent_outbound_only_one_succeeds(client):
    headers = await admin_headers(client)
    product = await _make_product(client, headers, sku="CC-1", name="Concurrent Widget")
    await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"pos": {"allow_negative_stock": False}}},
        headers=headers,
    )
    await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "5.00",
            "items": [{"product_id": product["id"], "quantity": "5", "unit_cost": "1.00"}],
        },
        headers=headers,
    )

    async def damage():
        return await client.post(
            "/api/v1/stock/damage",
            json={"items": [{"product_id": product["id"], "quantity": "5", "reason": "race"}]},
            headers=headers,
        )

    results = await asyncio.gather(damage(), damage())
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409], f"exactly one concurrent outbound must succeed: {statuses}"
    balance = await _balance(client, headers, product["id"])
    assert balance["quantity"] == Decimal("0.0000")
