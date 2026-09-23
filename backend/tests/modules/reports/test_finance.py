"""Finance Report backend — spec section 2.1.10 + section 7 Reports API.

Covers the finance summary cards, the combined income/expense entries table
(income derived from POS sales), and Add Expense (permission-gated, audited,
Decimal money). There is deliberately no frontend Expense page — API only.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from app.modules.reports.models import Expense
from app.shared.audit.models import AuditLog
from tests.modules.pos.helpers import make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login

FINANCE_ONLY_EMAIL = "finance-viewer@example.com"
FINANCE_ONLY_PASSWORD = "financepass1"
SALES_ONLY_EMAIL = "no-finance@example.com"
SALES_ONLY_PASSWORD = "salespass1"


@pytest.fixture
async def finance_only_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=FINANCE_ONLY_EMAIL,
        password=FINANCE_ONLY_PASSWORD,
        role_name="Finance Viewer",
        permissions=["report.finance"],
    )
    await db_session.commit()
    data = await login(client, FINANCE_ONLY_EMAIL, FINANCE_ONLY_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
async def sales_only_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=SALES_ONLY_EMAIL,
        password=SALES_ONLY_PASSWORD,
        role_name="Sales Only",
        permissions=["report.sales"],
    )
    await db_session.commit()
    data = await login(client, SALES_ONLY_EMAIL, SALES_ONLY_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
async def finance_baseline(client):
    headers = await admin_headers(client)
    response = await client.get("/api/v1/reports/finance", headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


def _today() -> date:
    """UTC date — the backend computes report periods in UTC."""
    return datetime.now(timezone.utc).date()


def _payload(**overrides) -> dict:
    payload = {
        "date": _today().isoformat(),
        "category": "Utilities",
        "description": "Electricity bill",
        "amount": "120.50",
        "payment_method": "CASH",
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


@pytest.mark.asyncio
async def test_create_expense_persists_decimal_amount_and_audits(client, db_session):
    headers = await admin_headers(client)
    response = await client.post(
        "/api/v1/reports/finance/expenses", json=_payload(amount="120.50"), headers=headers
    )
    assert response.status_code == 201, response.text
    row = response.json()["data"]
    # Money is stored as Decimal(18,2) — never binary floating point.
    assert Decimal(row["amount"]) == Decimal("120.50")
    assert row["category"] == "Utilities"
    assert row["payment_method"] == "CASH"
    assert row["expense_date"] == _today().isoformat()

    persisted = await db_session.execute(select(Expense).where(Expense.id == row["id"]))
    expense = persisted.scalar_one()
    assert isinstance(expense.amount, Decimal)
    assert expense.amount == Decimal("120.50")

    # Audit entry is required for the create.
    audit = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "expense", AuditLog.entity_id == expense.id)
        .order_by(AuditLog.created_at.desc())
    )
    entry = audit.scalars().first()
    assert entry is not None
    assert entry.action == "expense_created"
    assert entry.new_values["amount"] == "120.50"


@pytest.mark.asyncio
async def test_create_expense_rejects_invalid_amount(client):
    headers = await admin_headers(client)
    for amount in ["0", "-5.00", "0.00"]:
        response = await client.post(
            "/api/v1/reports/finance/expenses", json=_payload(amount=amount), headers=headers
        )
        assert response.status_code == 422, (amount, response.text)


@pytest.mark.asyncio
async def test_finance_summary_includes_operating_expenses_in_net_result(client, finance_baseline):
    headers = await admin_headers(client)
    response = await client.post(
        "/api/v1/reports/finance/expenses",
        json=_payload(amount="100.00", description="Rent"),
        headers=headers,
    )
    assert response.status_code == 201, response.text

    data = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    delta_expense = Decimal(data["total_expense"]) - Decimal(finance_baseline["total_expense"])
    assert delta_expense == Decimal("100.00")
    # Total Expense is the combined cash view (operating + supplier payments).
    assert Decimal(data["operating_expenses"]) + Decimal(data["supplier_payments"]) == Decimal(data["total_expense"])
    # P&L Net Result = Gross Profit - Damage - Expiry - OPERATING expenses
    # (supplier payments are cash flow, never a P&L expense).
    expected = (
        Decimal(data["gross_profit"])
        - Decimal(data["stock_damage_loss"])
        - Decimal(data["stock_expire_loss"])
        - Decimal(data["operating_expenses"])
    )
    assert Decimal(data["net_result"]) == expected
    assert Decimal(data["profit_and_loss"]["operating_profit"]) == expected
    # The expense reduced net result by exactly its amount.
    assert Decimal(finance_baseline["net_result"]) - Decimal(data["net_result"]) == Decimal("100.00")


@pytest.mark.asyncio
async def test_khr_expense_and_summary_normalization(client, finance_baseline):
    """Expenses carry their document currency; the Finance summary normalizes
    KHR amounts to USD via the exchange rate stored on the document."""
    headers = await admin_headers(client)
    response = await client.post(
        "/api/v1/reports/finance/expenses",
        json=_payload(amount="82000", currency="KHR", exchange_rate="41000", description="KHR riel ledger check"),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    row = response.json()["data"]
    assert row["currency"] == "KHR"
    assert Decimal(row["exchange_rate"]) == Decimal("41000")

    # The ledger row keeps the document currency.
    entries = (await client.get("/api/v1/reports/finance/entries?q=KHR riel ledger", headers=headers)).json()["data"]
    assert entries and entries[0]["currency"] == "KHR"
    assert Decimal(entries[0]["amount"]) == Decimal("82000.00")

    # Summary normalizes: 82000 KHR / 41000 = 2.00 USD.
    data = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    delta = Decimal(data["total_expense"]) - Decimal(finance_baseline["total_expense"])
    assert delta == Decimal("2.00")


@pytest.mark.asyncio
async def test_finance_entries_income_derived_from_sales_and_filters(client):
    headers = await admin_headers(client)
    # One sale to derive an income row from.
    tag = "FIN"
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"F-{tag}", "name": "Fin Cat"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"FIN-SKU-{tag}",
                "name": f"Fin Widget {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "25.00",
            },
            headers=headers,
        )
    ).json()["data"]
    sale = None
    supplier = (
        await client.post(
            "/api/v1/suppliers", json={"code": f"FIN-S-{tag}", "name": f"Fin Supplier {tag}"}, headers=headers
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "20.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    invoice_no = sale.json()["data"]["invoice_no"]

    expense = await client.post(
        "/api/v1/reports/finance/expenses",
        json=_payload(category="Transport", description=f"Fuel for delivery run {invoice_no}"),
        headers=headers,
    )
    assert expense.status_code == 201, expense.text

    # --- combined table (both types in one filtered page) ---------------------
    response = await client.get(f"/api/v1/reports/finance/entries?q={invoice_no}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 2  # the sale (income) + the expense row
    types = {row["type"] for row in payload["data"]}
    assert types == {"income", "expense"}

    income = next(r for r in payload["data"] if r["reference"] == invoice_no)
    assert income["type"] == "income"
    assert Decimal(income["amount"]) == Decimal("50.00")
    assert income["payment_method"] == "CASH"

    exp = next(r for r in payload["data"] if r["id"] == expense.json()["data"]["id"])
    assert exp["type"] == "expense"
    assert exp["reference"] == "Transport"
    assert Decimal(exp["amount"]) == Decimal("120.50")

    # --- type filter ------------------------------------------------------------
    only_income = await client.get("/api/v1/reports/finance/entries?type=INCOME", headers=headers)
    assert {r["type"] for r in only_income.json()["data"]} == {"income"}
    only_expense = await client.get("/api/v1/reports/finance/entries?type=EXPENSE", headers=headers)
    assert {r["type"] for r in only_expense.json()["data"]} == {"expense"}

    # --- search filter (invoice no and expense description) --------------------
    by_invoice = await client.get(f"/api/v1/reports/finance/entries?q={invoice_no}", headers=headers)
    assert by_invoice.status_code == 200
    references = {r["reference"] for r in by_invoice.json()["data"]}
    assert invoice_no in references

    by_search = await client.get("/api/v1/reports/finance/entries?q=Fuel", headers=headers)
    assert by_search.status_code == 200
    data = by_search.json()["data"]
    assert len(data) == 1 and data[0]["type"] == "expense"
    assert Decimal(data[0]["amount"]) == Decimal("120.50")

    # --- date range filter -------------------------------------------------------
    yesterday = (_today() - timedelta(days=1)).isoformat()
    tomorrow = (_today() + timedelta(days=1)).isoformat()
    ranged = await client.get(
        f"/api/v1/reports/finance/entries?q=Fuel&type=EXPENSE&startDate={yesterday}&endDate={tomorrow}",
        headers=headers,
    )
    assert ranged.status_code == 200
    assert ranged.json()["meta"]["total"] == 1

    future_only = await client.get(
        f"/api/v1/reports/finance/entries?q=Fuel&type=EXPENSE&startDate={tomorrow}&endDate={tomorrow}",
        headers=headers,
    )
    assert future_only.status_code == 200
    assert future_only.json()["meta"]["total"] == 0

    # --- pagination -------------------------------------------------------------
    paged = await client.get("/api/v1/reports/finance/entries?page=1&limit=1", headers=headers)
    assert paged.status_code == 200
    assert paged.json()["meta"]["limit"] == 1
    assert len(paged.json()["data"]) == 1


@pytest.mark.asyncio
async def test_finance_income_is_cash_received_not_credit_sales(client):
    """Cash-basis income: a credit sale is NOT income until the customer pays;
    each collection is its own income row for exactly the cash received."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"FINCB-{tag}", name=f"Fin Cash {tag}")
    customer = (
        await client.post(
            "/api/v1/customers",
            json={"code": f"FINCB-C-{tag}", "name": f"Fin Cash Customer {tag}"},
            headers=headers,
        )
    ).json()["data"]

    # Credit sale: 2 units fully on account, no cash received at checkout.
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "0",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    invoice_no = sale.json()["data"]["invoice_no"]
    sale_total = Decimal(sale.json()["data"]["grand_total"])
    assert sale_total > 0

    # No cash received yet → the unpaid credit sale produces no income row.
    before = (
        await client.get(f"/api/v1/reports/finance/entries?q={invoice_no}", headers=headers)
    ).json()["data"]
    assert [r for r in before if r["type"] == "income"] == []

    # Collect the debt → one income row for exactly the amount received.
    pay = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": str(sale_total), "payment_method": "CASH"},
        headers=headers,
    )
    assert pay.status_code == 201, pay.text

    after = (
        await client.get(f"/api/v1/reports/finance/entries?q={invoice_no}", headers=headers)
    ).json()["data"]
    income = [r for r in after if r["type"] == "income"]
    assert len(income) == 1
    assert Decimal(income[0]["amount"]) == sale_total
    assert income[0]["payment_method"] == "CASH"
    assert income[0]["reference"] == invoice_no


@pytest.mark.asyncio
async def test_finance_records_supplier_payments_as_expense(client, finance_baseline):
    """Cash paid to suppliers is Finance expense (income/expense logic):
    the payment made at purchase and every debt repayment reduce Net Result.
    Each payment is a single expense row, so a purchase and its repayment are
    never counted twice."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"FPAY-{tag}", "name": "Fin Pay Cat"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"FPAY-{tag}",
                "name": f"Fin Pay {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "3.00",
            },
            headers=headers,
        )
    ).json()["data"]
    supplier = (
        await client.post(
            "/api/v1/suppliers", json={"code": f"FPAY-S-{tag}", "name": f"Fin Pay Supplier {tag}"}, headers=headers
        )
    ).json()["data"]

    # Purchase 1: 10 @ 2.00 = 20.00, fully paid at receipt (STOCK_IN_PAYMENT).
    full = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "20.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert full.status_code == 201, full.text

    # Purchase 2: 5 @ 2.00 = 10.00, paying 2.00 now (8.00 on credit), then repaid.
    partial = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "2.00",
            "items": [{"product_id": product["id"], "quantity": "5", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert partial.status_code == 201, partial.text
    repay = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "8.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert repay.status_code == 201, repay.text

    data = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    # 20 (full purchase) + 2 (partial at receipt) + 8 (repayment) = 30.
    assert Decimal(data["supplier_payments"]) - Decimal(finance_baseline["supplier_payments"]) == Decimal("30.00")
    assert Decimal(data["total_expense"]) - Decimal(finance_baseline["total_expense"]) == Decimal("30.00")
    # Supplier payments do NOT reduce P&L (inventory cost is recognized through
    # COGS only) — they appear as cash-flow outflow instead.
    assert Decimal(data["net_result"]) - Decimal(finance_baseline["net_result"]) == Decimal("0.00")
    assert (
        Decimal(data["cash_flow"]["supplier_payments"])
        - Decimal(finance_baseline["cash_flow"]["supplier_payments"])
        == Decimal("30.00")
    )
    assert (
        Decimal(data["cash_flow"]["net_cash_flow"])
        - Decimal(finance_baseline["cash_flow"]["net_cash_flow"])
        == Decimal("-30.00")
    )

    # The combined ledger exposes each cash-out as an expense row.
    entries = (
        await client.get(
            f"/api/v1/reports/finance/entries?type=EXPENSE&q={supplier['name']}", headers=headers
        )
    ).json()["data"]
    assert entries, "supplier payments must appear in the finance ledger"
    assert all(row["type"] == "expense" for row in entries)
    assert all(row["currency"] == "USD" for row in entries)
    assert {row["category"] for row in entries} == {"Purchase", "Supplier Payment"}


@pytest.mark.asyncio
async def test_expense_create_requires_expense_create_permission(client, finance_only_headers):
    """report.finance alone can read but NOT create expenses."""
    response = await client.post(
        "/api/v1/reports/finance/expenses", json=_payload(), headers=finance_only_headers
    )
    assert response.status_code == 403, response.text

    # Reading remains allowed with report.finance.
    entries = await client.get("/api/v1/reports/finance/entries", headers=finance_only_headers)
    assert entries.status_code == 200
    summary = await client.get("/api/v1/reports/finance", headers=finance_only_headers)
    assert summary.status_code == 200


@pytest.mark.asyncio
async def test_finance_endpoints_require_report_finance_permission(client, sales_only_headers):
    for path in ["/api/v1/reports/finance", "/api/v1/reports/finance/entries"]:
        response = await client.get(path, headers=sales_only_headers)
        assert response.status_code == 403, (path, response.text)
    response = await client.post(
        "/api/v1/reports/finance/expenses", json=_payload(), headers=sales_only_headers
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_finance_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/reports/finance")).status_code == 401
    assert (await client.get("/api/v1/reports/finance/entries")).status_code == 401
    assert (await client.post("/api/v1/reports/finance/expenses", json=_payload())).status_code == 401
