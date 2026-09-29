"""Coverage for report endpoints the main suite does not exercise:
inventory valuation, stock reconciliation, and the purchase / debt CSV exports
(only /reports/sales/export was previously tested).

The test DB is shared for the session, so every product/supplier/customer is
uniquely tagged and assertions are scoped to those ids.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login


async def _make_product(client, headers, tag: str, *, track_batch: bool = True) -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"VAL-{tag}", "name": f"Val Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"VAL-{tag}",
            "name": f"Val Widget {tag}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "10.00",
            "track_batch": track_batch,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _stock_in(client, headers, product_id, *, qty, unit_cost, supplier_id=None, paid=None, batch_no=None, expiry=None):
    item = {"product_id": product_id, "quantity": qty, "unit_cost": unit_cost}
    if batch_no:
        item["batch_no"] = batch_no
    if expiry:
        item["expiry_date"] = expiry
    payload = {"paid_amount": paid if paid is not None else str(Decimal(unit_cost) * Decimal(qty)), "items": [item]}
    if supplier_id:
        payload["supplier_id"] = supplier_id
    response = await client.post("/api/v1/stock/in", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_supplier(client, headers, tag: str) -> dict:
    response = await client.post(
        "/api/v1/suppliers", json={"code": f"VAL-S-{tag}", "name": f"Val Supplier {tag}"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_customer(client, headers, tag: str) -> dict:
    response = await client.post(
        "/api/v1/customers", json={"code": f"VAL-C-{tag}", "name": f"Val Customer {tag}"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ------------------------------------------------------------- valuation / recon


@pytest.mark.asyncio
async def test_inventory_valuation_current_values_batch_ledger(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    today = date.today().isoformat()
    await _stock_in(client, headers, product["id"], qty="5", unit_cost="2.00", batch_no="LOT-A", expiry=today)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="3.00", batch_no="LOT-B", expiry=today)

    response = await client.get("/api/v1/reports/inventory-valuation", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    row = next(r for r in data["rows"] if r["product_id"] == product["id"])
    assert Decimal(str(row["quantity"])) == Decimal("15")
    assert Decimal(str(row["batch_quantity"])) == Decimal("15")
    # 5 × 2.00 + 10 × 3.00 = 40.00
    assert Decimal(str(row["value"])) == Decimal("40.00")
    assert Decimal(str(data["total_value"])) >= Decimal("40.00")

    # Selling from the oldest lot lowers the value by the lot's cost.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "1000.00", "items": [{"product_id": product["id"], "quantity": "2"}]},
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    response = await client.get("/api/v1/reports/inventory-valuation", headers=headers)
    row = next(r for r in response.json()["data"]["rows"] if r["product_id"] == product["id"])
    assert Decimal(str(row["quantity"])) == Decimal("13")
    # 3 remaining in LOT-A × 2.00 + 10 × 3.00 = 36.00
    assert Decimal(str(row["value"])) == Decimal("36.00")


@pytest.mark.asyncio
async def test_inventory_valuation_as_of_uses_movement_ledger(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="8", unit_cost="4.00", batch_no="LOT-A", expiry=date.today().isoformat())

    # Everything was received today, so an as-of date of yesterday sees zero.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = await client.get(
        "/api/v1/reports/inventory-valuation", params={"asOf": yesterday}, headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["as_of"] == yesterday
    row = next(r for r in payload["rows"] if r["product_id"] == product["id"])
    assert Decimal(str(row["quantity"])) == Decimal("0")
    assert Decimal(str(row["value"])) == Decimal("0.00")

    # As of today (movements included) the same lot is valued.
    response = await client.get(
        "/api/v1/reports/inventory-valuation", params={"asOf": date.today().isoformat()}, headers=headers
    )
    row = next(r for r in response.json()["data"]["rows"] if r["product_id"] == product["id"])
    assert Decimal(str(row["quantity"])) == Decimal("8")
    assert Decimal(str(row["value"])) == Decimal("32.00")


@pytest.mark.asyncio
async def test_stock_reconciliation_reports_consistent_stock(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="2.00", batch_no="LOT-A", expiry=date.today().isoformat())
    sale = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "1000.00", "items": [{"product_id": product["id"], "quantity": "3"}]},
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    response = await client.get("/api/v1/reports/stock-reconciliation", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "mismatch_count" in data and "mismatches" in data
    assert all(m["product_id"] != product["id"] for m in data["mismatches"]), data["mismatches"]


@pytest.mark.asyncio
async def test_stock_valuation_permissions(client, db_session):
    await create_user_with_role(
        db_session,
        email="val-no-access@example.com",
        password="valpass1",
        role_name="Val No Access",
        permissions=["report.sales"],
    )
    await db_session.commit()
    denied = await login(client, "val-no-access@example.com", "valpass1")
    denied_headers = {"Authorization": f"Bearer {denied['access_token']}"}
    for path in ("/api/v1/reports/inventory-valuation", "/api/v1/reports/stock-reconciliation"):
        response = await client.get(path, headers=denied_headers)
        assert response.status_code == 403, path

    tag = uuid.uuid4().hex[:6]
    await create_user_with_role(
        db_session,
        email=f"val-viewer-{tag}@example.com",
        password="valpass1",
        role_name=f"Val Viewer {tag}",
        permissions=["report.stock_valuation"],
    )
    await db_session.commit()
    granted = await login(client, f"val-viewer-{tag}@example.com", "valpass1")
    granted_headers = {"Authorization": f"Bearer {granted['access_token']}"}
    for path in ("/api/v1/reports/inventory-valuation", "/api/v1/reports/stock-reconciliation"):
        response = await client.get(path, headers=granted_headers)
        assert response.status_code == 200, path


# ---------------------------------------------------------------- CSV exports


@pytest.mark.asyncio
async def test_purchase_report_export_csv_and_plural_alias(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag, track_batch=False)
    supplier = await _make_supplier(client, headers, tag)
    stock_in = await _stock_in(
        client, headers, product["id"], qty="10", unit_cost="2.00", supplier_id=supplier["id"], paid="5.00"
    )
    document_no = stock_in["document_no"]
    assert document_no.startswith("STI-")

    for path in ("/api/v1/reports/purchase/export", "/api/v1/reports/purchases/export"):
        response = await client.get(path, params={"supplier_id": supplier["id"]}, headers=headers)
        assert response.status_code == 200, (path, response.text)
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        assert "Stock In / Purchase No." in body and "Remaining Supplier Debt" in body
        assert document_no in body
        assert supplier["name"] in body
        assert "15.00" in body  # remaining debt (20 total − 5 paid)


@pytest.mark.asyncio
async def test_customer_debt_report_export_csv(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag, track_batch=False)
    customer = await _make_customer(client, headers, tag)
    await _stock_in(client, headers, product["id"], qty="10", unit_cost="2.00")

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "5.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    invoice_no = sale.json()["data"]["invoice_no"]

    response = await client.get(
        "/api/v1/reports/customer-debts/export", params={"customer_id": customer["id"]}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "Remaining Amount" in body
    assert customer["name"] in body and invoice_no in body
    assert "15.00" in body  # invoice total 20.00 − deposit 5.00

    # The CSV endpoint accepts the request without the JSON-only user_id filter.
    tolerant = await client.get(
        "/api/v1/reports/customer-debts/export",
        params={"customer_id": customer["id"], "user_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert tolerant.status_code == 200, tolerant.text


@pytest.mark.asyncio
async def test_supplier_debt_report_export_csv(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await _make_product(client, headers, tag, track_batch=False)
    supplier = await _make_supplier(client, headers, tag)
    stock_in = await _stock_in(
        client, headers, product["id"], qty="10", unit_cost="2.00", supplier_id=supplier["id"], paid="5.00"
    )
    document_no = stock_in["document_no"]

    response = await client.get(
        "/api/v1/reports/supplier-debts/export", params={"supplier_id": supplier["id"]}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "Remaining Amount" in body
    assert supplier["name"] in body and document_no in body
    assert "15.00" in body
