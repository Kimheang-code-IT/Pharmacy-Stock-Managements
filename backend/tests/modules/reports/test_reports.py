"""Reports endpoints — verify metrics against transaction data (spec 2.1.10).

The test database is shared across the pytest session: list reports are
isolated by unique product/customer/supplier filters, and the finance report
is asserted as a delta against a pre-seed baseline.
"""

from decimal import Decimal

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login

SALES_ONLY_EMAIL = "sales-clerk@example.com"
SALES_ONLY_PASSWORD = "clerkpass1"


@pytest.fixture
async def sales_only_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=SALES_ONLY_EMAIL,
        password=SALES_ONLY_PASSWORD,
        role_name="Sales Clerk",
        permissions=["report.sales"],
    )
    await db_session.commit()
    data = await login(client, SALES_ONLY_EMAIL, SALES_ONLY_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _seed(client, headers):
    """Supplier stock in 10@2 (paid 5, debt 15); cash sale 3@10 with a partial
    return of 1; debt sale 2@10 (deposit 5, debt 15); damage 1@2.
    Finance deltas: sales +40, purchase +20, customer debt +15, supplier debt
    +15, COGS +8, damage +2, gross +32, net +30."""
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:6]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"REP-{tag}", "name": "Rep Cat"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={"sku": f"REP-{tag}", "name": f"Rep Widget {tag}", "category_id": category["id"], "uom_id": str(DEFAULT_UOM_ID), "selling_price": "10.00"},
            headers=headers,
        )
    ).json()["data"]
    supplier = (
        await client.post(
            "/api/v1/suppliers", json={"code": f"REP-S-{tag}", "name": f"Rep Supplier {tag}"}, headers=headers
        )
    ).json()["data"]
    customer = (
        await client.post(
            "/api/v1/customers", json={"code": f"REP-C-{tag}", "name": f"Rep Customer {tag}"}, headers=headers
        )
    ).json()["data"]

    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "5.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text

    cash_sale = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "100.00", "items": [{"product_id": product["id"], "quantity": "3"}]},
        headers=headers,
    )
    assert cash_sale.status_code == 201, cash_sale.text
    cash_sale = cash_sale.json()["data"]

    debt_sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "5.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert debt_sale.status_code == 201, debt_sale.text
    debt_sale = debt_sale.json()["data"]

    # Return 1 unit of the cash sale (restocked).
    sale_return = await client.post(
        f"/api/v1/pos/sales/{cash_sale['id']}/return",
        json={
            "reason": "changed mind",
            "items": [{"sale_item_id": cash_sale["items"][0]["id"], "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert sale_return.status_code == 201, sale_return.text

    damage = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": product["id"], "quantity": "1", "reason": "dropped"}]},
        headers=headers,
    )
    assert damage.status_code == 201, damage.text

    return {
        "product": product,
        "supplier": supplier,
        "customer": customer,
        "stock_in": stock_in.json()["data"],
        "cash_sale": cash_sale,
        "debt_sale": debt_sale,
    }


def _delta(baseline: dict, after: dict, key: str) -> Decimal:
    return Decimal(str(after[key])) - Decimal(str(baseline[key]))


@pytest.fixture
async def finance_baseline(client):
    headers = await admin_headers(client)
    response = await client.get("/api/v1/reports/finance", headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_sales_report_metrics_and_filters(client):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)
    product_id = seeded["product"]["id"]

    response = await client.get(f"/api/v1/reports/sales?product_id={product_id}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 2
    rows = {r["payment_method"]: r for r in payload["data"]}
    assert set(rows) == {"CASH", "CUSTOMER_DEBT"}

    cash = rows["CASH"]
    assert cash["invoice_no"] == seeded["cash_sale"]["invoice_no"]
    assert Decimal(cash["quantity"]) == Decimal("3")
    assert Decimal(cash["sales_amount"]) == Decimal("30.00")
    assert Decimal(cash["return_amount"]) == Decimal("10.00")
    assert Decimal(cash["net_quantity"]) == Decimal("2")
    assert Decimal(cash["cost"]) == Decimal("4.00")
    assert Decimal(cash["gross_profit"]) == Decimal("16.00")

    debt = rows["CUSTOMER_DEBT"]
    assert debt["invoice_no"] == seeded["debt_sale"]["invoice_no"]
    assert debt["customer_name"] == f"Rep Customer {seeded['customer']['code'].split('-')[-1]}"
    assert Decimal(debt["sales_amount"]) == Decimal("20.00")
    assert Decimal(debt["gross_profit"]) == Decimal("16.00")

    # Filter by payment method.
    only_cash = await client.get(
        f"/api/v1/reports/sales?product_id={product_id}&payment_method=CASH", headers=headers
    )
    assert only_cash.json()["meta"]["total"] == 1

    # Filter by invoice.
    by_invoice = await client.get(
        f"/api/v1/reports/sales?q={seeded['debt_sale']['invoice_no']}", headers=headers
    )
    assert by_invoice.json()["meta"]["total"] == 1

    # Filter by category.
    by_category = await client.get(
        f"/api/v1/reports/sales?category_id={seeded['product']['category_id']}", headers=headers
    )
    assert by_category.json()["meta"]["total"] >= 2


@pytest.mark.asyncio
async def test_purchase_report_shows_paid_and_remaining(client):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    response = await client.get(
        f"/api/v1/reports/purchase?supplier_id={seeded['supplier']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    row = payload["data"][0]
    assert row["document_no"].startswith("STI-")
    assert row["supplier_name"] == f"Rep Supplier {seeded['supplier']['code'].split('-')[-1]}"
    assert Decimal(row["quantity"]) == Decimal("10")
    assert Decimal(row["cost_price"]) == Decimal("2.00")
    assert Decimal(row["total_cost"]) == Decimal("20.00")
    assert Decimal(row["paid_amount"]) == Decimal("5.00")
    assert Decimal(row["remaining_debt"]) == Decimal("15.00")
    assert row["status"] == "PARTIAL"

    # Status filter.
    confirmed = await client.get(
        f"/api/v1/reports/purchase?supplier_id={seeded['supplier']['id']}&status=CONFIRMED", headers=headers
    )
    assert confirmed.json()["meta"]["total"] == 1
    none = await client.get(
        f"/api/v1/reports/purchase?supplier_id={seeded['supplier']['id']}&status=DRAFT", headers=headers
    )
    assert none.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_customer_debt_report_and_payment_history_link(client):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    response = await client.get(f"/api/v1/reports/customer-debts?q={seeded['customer']['code']}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    row = payload["data"][0]
    assert row["customer_name"] == f"Rep Customer {seeded['customer']['code'].split('-')[-1]}"
    assert row["customer_id"] == seeded["customer"]["id"]
    assert row["invoice_no"] == seeded["debt_sale"]["invoice_no"]
    # Date is the invoice/sale date, not the debt record creation time.
    assert row["date"] == seeded["debt_sale"]["sale_date"]
    assert Decimal(row["invoice_total"]) == Decimal("20.00")
    assert Decimal(row["paid_amount"]) == Decimal("5.00")
    assert Decimal(row["remaining_amount"]) == Decimal("15.00")
    assert row["status"] == "PARTIAL"

    # Payment history remains available (immutable payments from Phase 4).
    history = await client.get(
        f"/api/v1/customers/{seeded['customer']['id']}/debts/{row['debt_id']}/payments", headers=headers
    )
    assert history.status_code == 200
    assert len(history.json()["data"]) == 1  # the 5.00 deposit


@pytest.mark.asyncio
async def test_supplier_debt_report(client):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    response = await client.get(f"/api/v1/reports/supplier-debts?q={seeded['supplier']['code']}", headers=headers)
    assert response.status_code == 200, response.text
    row = response.json()["data"][0]
    assert row["supplier_name"] == f"Rep Supplier {seeded['supplier']['code'].split('-')[-1]}"
    assert row["supplier_id"] == seeded["supplier"]["id"]
    assert row["document_no"] == seeded["stock_in"]["document_no"]
    # Date is the stock-in / purchase date.
    assert row["date"] == seeded["stock_in"]["transaction_date"]
    assert Decimal(row["total_amount"]) == Decimal("20.00")
    assert Decimal(row["paid_amount"]) == Decimal("5.00")
    assert Decimal(row["remaining_amount"]) == Decimal("15.00")
    assert row["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_debt_reports_rows_filters_and_unpaid_inclusion(client):
    """Both debt reports list document-level rows (spec 2.1.10): unpaid and
    partial debts included, with party/date-range/status filters."""
    from datetime import datetime, timedelta, timezone

    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    # Zero-deposit debt sale -> an UNPAID customer debt document.
    unpaid_sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": seeded["customer"]["id"],
            "amount_received": "0.00",
            "items": [{"product_id": seeded["product"]["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert unpaid_sale.status_code == 201, unpaid_sale.text
    unpaid_sale = unpaid_sale.json()["data"]

    # --- Customer debt report -------------------------------------------------
    response = await client.get(
        f"/api/v1/reports/customer-debts?customer_id={seeded['customer']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 2
    by_status = {r["status"]: r for r in payload["data"]}
    assert set(by_status) == {"PARTIAL", "UNPAID"}

    partial = by_status["PARTIAL"]
    assert set(partial) >= {
        "date", "invoice_no", "customer_id", "customer_name", "invoice_total",
        "paid_amount", "remaining_amount", "due_date", "status",
    }
    assert partial["invoice_no"] == seeded["debt_sale"]["invoice_no"]
    unpaid = by_status["UNPAID"]
    assert unpaid["invoice_no"] == unpaid_sale["invoice_no"]
    assert Decimal(unpaid["paid_amount"]) == Decimal("0.00")
    assert Decimal(unpaid["remaining_amount"]) == Decimal("10.00")

    # Status filter.
    only_unpaid = await client.get(
        f"/api/v1/reports/customer-debts?customer_id={seeded['customer']['id']}&status=UNPAID",
        headers=headers,
    )
    assert only_unpaid.json()["meta"]["total"] == 1
    assert only_unpaid.json()["data"][0]["invoice_no"] == unpaid_sale["invoice_no"]

    # Party filter excludes other customers.
    other_customer = (
        await client.post(
            "/api/v1/customers",
            json={"code": f"REP-C2-{seeded['customer']['code'].split('-')[-1]}", "name": "Rep Other Customer"},
            headers=headers,
        )
    ).json()["data"]
    none = await client.get(
        f"/api/v1/reports/customer-debts?customer_id={other_customer['id']}", headers=headers
    )
    assert none.json()["meta"]["total"] == 0

    # Date range filter on the invoice/sale date: today matches, last month doesn't.
    today = datetime.now(timezone.utc).date().isoformat()
    month_old = (datetime.now(timezone.utc).date() - timedelta(days=40)).isoformat()
    in_range = await client.get(
        f"/api/v1/reports/customer-debts?customer_id={seeded['customer']['id']}"
        f"&startDate={today}&endDate={today}",
        headers=headers,
    )
    assert in_range.json()["meta"]["total"] == 2
    out_of_range = await client.get(
        f"/api/v1/reports/customer-debts?customer_id={seeded['customer']['id']}"
        f"&startDate={month_old}&endDate={month_old}",
        headers=headers,
    )
    assert out_of_range.json()["meta"]["total"] == 0

    # --- Supplier debt report -------------------------------------------------
    response = await client.get(
        f"/api/v1/reports/supplier-debts?supplier_id={seeded['supplier']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    row = payload["data"][0]
    assert set(row) >= {
        "date", "document_no", "supplier_id", "supplier_name", "total_amount",
        "paid_amount", "remaining_amount", "due_date", "status",
    }
    assert row["status"] == "PARTIAL"  # partial supplier debt included

    only_paid = await client.get(
        f"/api/v1/reports/supplier-debts?supplier_id={seeded['supplier']['id']}&status=PAID",
        headers=headers,
    )
    assert only_paid.json()["meta"]["total"] == 0

    out_of_range = await client.get(
        f"/api/v1/reports/supplier-debts?supplier_id={seeded['supplier']['id']}"
        f"&startDate={month_old}&endDate={month_old}",
        headers=headers,
    )
    assert out_of_range.json()["meta"]["total"] == 0

    # Party filter excludes other suppliers.
    other_supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": f"REP-S2-{seeded['supplier']['code'].split('-')[-1]}", "name": "Rep Other Supplier"},
            headers=headers,
        )
    ).json()["data"]
    none = await client.get(
        f"/api/v1/reports/supplier-debts?supplier_id={other_supplier['id']}", headers=headers
    )
    assert none.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_finance_report_reconciles_with_transactions(client, finance_baseline):
    headers = await admin_headers(client)
    await _seed(client, headers)

    response = await client.get("/api/v1/reports/finance", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert _delta(finance_baseline, data, "total_sales") == Decimal("40.00")
    assert _delta(finance_baseline, data, "total_purchase_cost") == Decimal("20.00")
    assert _delta(finance_baseline, data, "total_customer_debt") == Decimal("15.00")
    assert _delta(finance_baseline, data, "total_supplier_debt") == Decimal("15.00")
    assert _delta(finance_baseline, data, "cost_of_goods_sold") == Decimal("8.00")
    assert _delta(finance_baseline, data, "stock_damage_loss") == Decimal("2.00")
    assert _delta(finance_baseline, data, "stock_expire_loss") == Decimal("0.00")
    # Gross profit = 40 - 8 = 32; Net = 32 - 2 damage - 0 expiry = 30.
    assert _delta(finance_baseline, data, "gross_profit") == Decimal("32.00")
    assert _delta(finance_baseline, data, "net_result") == Decimal("30.00")


@pytest.mark.asyncio
async def test_sales_report_export_csv(client):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    response = await client.get(
        f"/api/v1/reports/sales/export?product_id={seeded['product']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "Invoice No." in body and "Gross Profit" in body
    assert seeded["cash_sale"]["invoice_no"] in body
    assert seeded["debt_sale"]["invoice_no"] in body


@pytest.mark.asyncio
async def test_report_permissions_are_enforced(client, sales_only_headers):
    headers = await admin_headers(client)
    seeded = await _seed(client, headers)

    # report.sales holder can open the sales report...
    allowed = await client.get(
        f"/api/v1/reports/sales?product_id={seeded['product']['id']}", headers=sales_only_headers
    )
    assert allowed.status_code == 200

    # ...but not finance or purchase.
    denied_finance = await client.get("/api/v1/reports/finance", headers=sales_only_headers)
    assert denied_finance.status_code == 403
    denied_purchase = await client.get("/api/v1/reports/purchase", headers=sales_only_headers)
    assert denied_purchase.status_code == 403
    denied_debts = await client.get("/api/v1/reports/customer-debts", headers=sales_only_headers)
    assert denied_debts.status_code == 403

    # Export shares its report's permission.
    allowed_export = await client.get(
        f"/api/v1/reports/sales/export?product_id={seeded['product']['id']}", headers=sales_only_headers
    )
    assert allowed_export.status_code == 200
