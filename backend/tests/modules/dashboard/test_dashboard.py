"""Dashboard summary metrics — verify against transaction data (spec 2.1.1).

The test database is shared across the whole pytest session, so metrics are
asserted as *deltas* against a baseline captured before each test seeds.
"""

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login

VIEWER_EMAIL = "dash-viewer@example.com"
VIEWER_PASSWORD = "viewerpass1"


@pytest.fixture
async def dashboard_viewer_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=VIEWER_EMAIL,
        password=VIEWER_PASSWORD,
        role_name="Dashboard Viewer",
        permissions=["dashboard.view"],
    )
    await db_session.commit()
    data = await login(client, VIEWER_EMAIL, VIEWER_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _seed_transactions(client, headers):
    """1 product: stock in 10@2, cash sale 3@10, debt sale 2@10 (no deposit),
    damage 1 unit, operating expense 20. Deltas: income +50, expense +20,
    damage loss +2, COGS +10, gross profit +40, customer debt +20."""
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:6]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"DASH-{tag}", "name": f"Dash Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"DASH-{tag}",
                "name": f"Dash Widget {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
                "minimum_stock": "4",
            },
            headers=headers,
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={"paid_amount": "20.00", "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}]},
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text

    cash = await client.post(
        "/api/v1/pos/sales",
        json={"payment_method": "CASH", "amount_received": "50.00", "items": [{"product_id": product["id"], "quantity": "3"}]},
        headers=headers,
    )
    assert cash.status_code == 201, cash.text

    customer = (
        await client.post(
            "/api/v1/customers", json={"code": f"DASH-C-{tag}", "name": "Dash Customer"}, headers=headers
        )
    ).json()["data"]
    debt_sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert debt_sale.status_code == 201, debt_sale.text

    damage = await client.post(
        "/api/v1/stock/damage",
        json={"items": [{"product_id": product["id"], "quantity": "1", "reason": "dropped"}]},
        headers=headers,
    )
    assert damage.status_code == 201, damage.text

    # Dashboard Expense = operating expenses (aligned with Finance, spec 2.1.10).
    expense = await client.post(
        "/api/v1/reports/finance/expenses",
        json={
            "date": datetime.now(timezone.utc).date().isoformat(),
            "category": "Utilities",
            "amount": "20.00",
            "payment_method": "CASH",
        },
        headers=headers,
    )
    assert expense.status_code == 201, expense.text
    return product, customer, cash.json()["data"]


def _delta(baseline: dict, after: dict, *path) -> Decimal:
    value = Decimal("0")
    for payload in (baseline, after):
        node = payload
        for key in path:
            node = node[key]
        value = (value - Decimal(str(node))) if payload is baseline else (value + Decimal(str(node)))
    return value


@pytest.fixture
async def dashboard_baseline(client):
    headers = await admin_headers(client)
    response = await client.get("/api/v1/dashboard/summary?period=7d", headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_dashboard_summary_reconciles_with_transactions(client, dashboard_baseline):
    headers = await admin_headers(client)
    product, _, cash_sale = await _seed_transactions(client, headers)

    response = await client.get("/api/v1/dashboard/summary?period=7d", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["profit_visible"] is True
    assert _delta(dashboard_baseline, data, "cards", "today_sales") == Decimal("50.00")
    assert _delta(dashboard_baseline, data, "cards", "today_sales_count") == Decimal("2")
    assert _delta(dashboard_baseline, data, "cards", "customer_debt") == Decimal("20.00")
    assert _delta(dashboard_baseline, data, "cards", "supplier_debt") == Decimal("0.00")
    assert _delta(dashboard_baseline, data, "cards", "gross_profit") == Decimal("40.00")

    assert _delta(dashboard_baseline, data, "summary", "total_income") == Decimal("50.00")
    assert _delta(dashboard_baseline, data, "summary", "total_expense") == Decimal("20.00")
    assert _delta(dashboard_baseline, data, "summary", "gross_profit") == Decimal("40.00")
    # Net income = gross profit (40) - damage loss (2) - expiry loss (0)
    # - operating expenses (20).
    assert _delta(dashboard_baseline, data, "summary", "net_income") == Decimal("18.00")
    # Both seeded sales happened today, i.e. inside the calendar month.
    assert _delta(dashboard_baseline, data, "summary", "sales_this_month_count") == Decimal("2")
    assert _delta(dashboard_baseline, data, "summary", "sales_this_month_amount") == Decimal("50.00")
    assert _delta(dashboard_baseline, data, "summary", "customer_debt") == Decimal("20.00")
    assert _delta(dashboard_baseline, data, "summary", "damage_loss") == Decimal("2.00")
    assert _delta(dashboard_baseline, data, "summary", "expiry_loss") == Decimal("0.00")
    assert isinstance(data["summary"]["pending_delivery_notes_count"], int)

    # Chart: exactly 7 points for 7d; today's bucket carries the deltas.
    chart = data["chart"]
    assert len(chart) == 7
    assert Decimal(chart[-1]["income"]) - Decimal(dashboard_baseline["chart"][-1]["income"]) == Decimal("50.00")
    assert Decimal(chart[-1]["expense"]) - Decimal(dashboard_baseline["chart"][-1]["expense"]) == Decimal("20.00")
    assert int(chart[-1]["sales_count"]) - int(dashboard_baseline["chart"][-1]["sales_count"]) == 2

    extras = data["extras"]
    assert len(extras["recent_sales"]) >= 2
    assert len(extras["recent_stock_activity"]) >= 3
    top = next((t for t in extras["top_products"] if t["product_id"] == product["id"]), None)
    # With a polluted shared database the seeded product may fall out of the
    # global top 5; when it is listed its totals must reconcile exactly.
    if top is not None:
        assert Decimal(top["quantity_sold"]) == Decimal("5.00")
        assert Decimal(top["sales_amount"]) == Decimal("50.00")
    # 10 in, 5 sold, 1 damaged -> 4 left == minimum_stock 4 => low stock.
    assert _delta(dashboard_baseline, data, "extras", "low_stock_count") == Decimal("1.00")
    assert _delta(dashboard_baseline, data, "extras", "out_of_stock_count") == Decimal("0.00")


@pytest.mark.asyncio
async def test_dashboard_month_and_custom_periods(client, dashboard_baseline):
    headers = await admin_headers(client)
    product, _, _ = await _seed_transactions(client, headers)

    # The month baseline is polluted by this seed; assert shape instead.
    after_month = await client.get("/api/v1/dashboard/summary?period=month", headers=headers)
    assert after_month.status_code == 200
    month_data = after_month.json()["data"]
    assert month_data["period_start"] == month_data["chart"][0]["date"]

    today = month_data["period_end"]
    custom = await client.get(
        f"/api/v1/dashboard/summary?period=custom&startDate={today}&endDate={today}", headers=headers
    )
    assert custom.status_code == 200
    custom_data = custom.json()["data"]
    assert len(custom_data["chart"]) == 1
    assert Decimal(custom_data["chart"][0]["income"]) - Decimal(
        dashboard_baseline["chart"][-1]["income"]
    ) >= Decimal("50.00")

    bad = await client.get("/api/v1/dashboard/summary?period=custom", headers=headers)
    assert bad.status_code == 422

    swapped = await client.get(
        f"/api/v1/dashboard/summary?period=custom&endDate={today}&startDate={today}", headers=headers
    )
    assert swapped.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_counts_pending_delivery_notes(client, dashboard_baseline):
    """Delivery notes count as pending until delivered; delivered ones drop out."""
    headers = await admin_headers(client)
    _, _, cash_sale = await _seed_transactions(client, headers)

    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "sale_id": cash_sale["id"],
            "delivery_phone": "0123456789",
            "delivery_location": "Street 1, Phnom Penh",
            "items": [{"sale_item_id": cash_sale["items"][0]["id"], "qty_to_deliver": "3"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()["data"]

    after_create = await client.get("/api/v1/dashboard/summary?period=7d", headers=headers)
    assert after_create.status_code == 200
    assert _delta(dashboard_baseline, after_create.json()["data"], "summary", "pending_delivery_notes_count") == 1

    confirmed = await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text

    delivered = await client.post(f"/api/v1/delivery-notes/{note['id']}/deliver", headers=headers)
    assert delivered.status_code == 200, delivered.text

    after_deliver = await client.get("/api/v1/dashboard/summary?period=7d", headers=headers)
    assert after_deliver.status_code == 200
    assert _delta(dashboard_baseline, after_deliver.json()["data"], "summary", "pending_delivery_notes_count") == 0


@pytest.mark.asyncio
async def test_dashboard_hides_profit_without_permission(client, dashboard_viewer_headers, dashboard_baseline):
    headers = await admin_headers(client)
    await _seed_transactions(client, headers)

    response = await client.get("/api/v1/dashboard/summary?period=7d", headers=dashboard_viewer_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["profit_visible"] is False
    assert data["cards"]["gross_profit"] is None
    assert data["summary"]["gross_profit"] is None
    assert data["summary"]["net_income"] is None
    # Non-sensitive values still visible.
    assert _delta(dashboard_baseline, data, "cards", "today_sales") == Decimal("50.00")
    assert _delta(dashboard_baseline, data, "summary", "total_income") == Decimal("50.00")
    assert _delta(dashboard_baseline, data, "summary", "sales_this_month_count") == Decimal("2")
    assert _delta(dashboard_baseline, data, "summary", "damage_loss") == Decimal("2.00")
    assert _delta(dashboard_baseline, data, "summary", "pending_delivery_notes_count") == 0


@pytest.mark.asyncio
async def test_dashboard_requires_permission(client, db_session):
    await create_user_with_role(
        db_session,
        email="dash-denied@example.com",
        password="deniedpass1",
        role_name="Dash Denied",
        permissions=["pos.access"],
    )
    await db_session.commit()
    data = await login(client, "dash-denied@example.com", "deniedpass1")
    denied = {"Authorization": f"Bearer {data['access_token']}"}

    response = await client.get("/api/v1/dashboard/summary", headers=denied)
    assert response.status_code == 403
