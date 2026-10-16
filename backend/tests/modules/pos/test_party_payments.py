"""Flat party-level payment endpoints (frontend fallback when no debt row is
selected): settle open debts oldest-first in one transaction, reject
overpayment, immutable payment rows, server-side permissions."""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login


async def _two_customer_debts(client, headers, tag: str):
    """Customer with two open debts: 20.00 then 10.00 (oldest first)."""
    product = await make_stocked_product(client, headers, sku=f"CPAY-{tag}", name=f"Pay Widget {tag}", qty="10")
    customer = await make_customer(client, headers, code=f"CPAY-C-{tag}", name=f"Pay Cust {tag}")
    invoice_nos: list[str] = []
    for quantity in ("2", "1"):
        sale = await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CUSTOMER_DEBT",
                "customer_id": customer["id"],
                "items": [{"product_id": product["id"], "quantity": quantity}],
            },
            headers=headers,
        )
        assert sale.status_code == 201, sale.text
        invoice_nos.append(sale.json()["data"]["invoice_no"])
    debts = (await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)).json()["data"]
    assert len(debts) == 2
    return customer, debts, invoice_nos


@pytest.mark.asyncio
async def test_customer_level_payment_settles_oldest_first(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts, invoice_nos = await _two_customer_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "25.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    payments = response.json()["data"]
    # 25.00 splits: 20.00 onto the oldest debt, 5.00 onto the next.
    assert len(payments) == 2
    assert Decimal(payments[0]["amount"]) == Decimal("20.00")
    assert Decimal(payments[1]["amount"]) == Decimal("5.00")
    assert payments[0]["customer_debt_id"] == debts[0]["id"]

    after = (await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)).json()["data"]
    by_id = {row["id"]: row for row in after}
    assert by_id[debts[0]["id"]]["status"] == "PAID"
    assert Decimal(by_id[debts[0]["id"]]["remaining_amount"]) == Decimal("0.00")
    assert by_id[debts[1]["id"]]["status"] == "PARTIAL"
    assert Decimal(by_id[debts[1]["id"]]["remaining_amount"]) == Decimal("5.00")

    history = await client.get(f"/api/v1/customers/{customer['id']}/payments", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["data"]) == 2

    # The linked SALES follow the collection (Sales Report + customer history
    # read the sale's paid/remaining/status): oldest invoice → Paid, next one
    # → Partial. This is what "update the customer to paid" needs.
    async def _sale_row(invoice_no: str) -> dict:
        report = await client.get("/api/v1/reports/sales", params={"q": invoice_no}, headers=headers)
        assert report.status_code == 200, report.text
        return report.json()["data"][0]

    first = await _sale_row(invoice_nos[0])
    assert Decimal(first["paid_amount"]) == Decimal("20.00")
    assert Decimal(first["debt_amount"]) == Decimal("0.00")
    assert first["payment_status"] == "PAID"

    second = await _sale_row(invoice_nos[1])
    assert Decimal(second["paid_amount"]) == Decimal("5.00")
    assert Decimal(second["debt_amount"]) == Decimal("5.00")
    assert second["payment_status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_customer_level_payment_rejects_overpayment(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts, _invoice_nos = await _two_customer_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "31.00", "payment_method": "CASH"},  # outstanding is 30.00
        headers=headers,
    )
    assert response.status_code == 422
    assert "exceeds" in response.text


@pytest.mark.asyncio
async def test_customer_level_payment_currency_filter(client):
    """Party payments from the debt report target ONE currency: paying the KHR
    row must not touch the older USD debt (and vice versa)."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(
        client, headers, sku=f"CPAY-CUR-{tag}", name=f"Cur Widget {tag}", qty="10"
    )
    customer = await make_customer(
        client, headers, code=f"CPAY-CUR-C-{tag}", name=f"Cur Cust {tag}"
    )
    # Oldest first: a USD debt (2 × 10.00 = 20.00), then a KHR debt.
    usd_sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert usd_sale.status_code == 201, usd_sale.text
    khr_sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "currency": "KHR",
            "exchange_rate": "41000",
            "items": [{"product_id": product["id"], "quantity": "1", "unit_price": "410000"}],
        },
        headers=headers,
    )
    assert khr_sale.status_code == 201, khr_sale.text
    khr_invoice_no = khr_sale.json()["data"]["invoice_no"]

    debts = (await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)).json()["data"]
    usd_debt = next(row for row in debts if row["currency"] == "USD")
    khr_debt = next(row for row in debts if row["currency"] == "KHR")

    # Settle only the KHR side even though the USD debt is older.
    paid = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "410000", "payment_method": "CASH", "currency": "KHR"},
        headers=headers,
    )
    assert paid.status_code == 201, paid.text
    payments = paid.json()["data"]
    assert len(payments) == 1
    assert payments[0]["customer_debt_id"] == khr_debt["id"]

    after = {
        row["id"]: row
        for row in (
            await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
        ).json()["data"]
    }
    assert after[khr_debt["id"]]["status"] == "PAID"
    assert after[usd_debt["id"]]["status"] != "PAID"
    assert Decimal(after[usd_debt["id"]]["remaining_amount"]) == Decimal("20.00")

    # The single-debt payment flow mirrors onto the KHR sale too.
    khr_report = await client.get(
        "/api/v1/reports/sales", params={"q": khr_invoice_no}, headers=headers
    )
    assert khr_report.status_code == 200, khr_report.text
    khr_row = khr_report.json()["data"][0]
    assert Decimal(khr_row["paid_amount"]) == Decimal("410000.00")
    assert Decimal(khr_row["debt_amount"]) == Decimal("0.00")
    assert khr_row["payment_status"] == "PAID"


@pytest.mark.asyncio
async def test_customer_list_outstanding_debt_is_live(client):
    """The Customers list 'Outstanding Debt' column reads the live per-currency
    open balances: both currencies listed before payment, only the unpaid one
    after (a paid-off debt drops straight out of the column)."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(
        client, headers, sku=f"CLIST-{tag}", name=f"List Widget {tag}", qty="10"
    )
    customer = await make_customer(
        client, headers, code=f"CLIST-C-{tag}", name=f"List Cust {tag}"
    )
    for sale in (
        {
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        {
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "currency": "KHR",
            "exchange_rate": "41000",
            "items": [{"product_id": product["id"], "quantity": "1", "unit_price": "410000"}],
        },
    ):
        created = await client.post("/api/v1/pos/sales", json=sale, headers=headers)
        assert created.status_code == 201, created.text

    async def _listed_row() -> dict:
        response = await client.get(
            "/api/v1/customers", params={"q": customer["name"]}, headers=headers
        )
        assert response.status_code == 200, response.text
        return next(row for row in response.json()["data"] if row["id"] == customer["id"])

    assert (await _listed_row())["debt_balances"] == {
        "USD": "20.0000",
        "KHR": "410000.0000",
    }

    paid = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "410000", "payment_method": "CASH", "currency": "KHR"},
        headers=headers,
    )
    assert paid.status_code == 201, paid.text
    # The KHR debt is settled — the list now shows only the USD balance.
    assert (await _listed_row())["debt_balances"] == {"USD": "20.0000"}


@pytest.mark.asyncio
async def test_customer_level_payment_requires_permission(client, db_session):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, debts, _invoice_nos = await _two_customer_debts(client, headers, tag)

    await create_user_with_role(
        db_session,
        email=f"cpay-{tag}@example.com",
        password="cpaypass1",
        role_name=f"Customer Pay Viewer {tag}",
        permissions=["customer.view"],
    )
    await db_session.commit()
    viewer = await login(client, f"cpay-{tag}@example.com", "cpaypass1")
    viewer_headers = {"Authorization": f"Bearer {viewer['access_token']}"}

    denied = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403


async def _supplier_with_two_debts(client, headers, tag: str):
    """Supplier with two open stock-in debts: 15.00 then 5.00 remaining."""
    supplier = (
        await client.post(
            "/api/v1/suppliers",
            json={"code": f"SPAY-{tag}", "name": f"Pay Supplier {tag}", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"SPAY-CAT-{tag}", "name": f"Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"SPAY-P-{tag}",
                "name": f"Pay Product {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
            },
            headers=headers,
        )
    ).json()["data"]
    for paid in ("5.00", "15.00"):
        stock_in = await client.post(
            "/api/v1/stock/in",
            json={
                "supplier_id": supplier["id"],
                "paid_amount": paid,
                "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
            },
            headers=headers,
        )
        assert stock_in.status_code == 201, stock_in.text
    debts = (await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)).json()["data"]
    assert len(debts) == 2
    return supplier, debts


@pytest.mark.asyncio
async def test_supplier_level_payment_settles_oldest_first(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    supplier, debts = await _supplier_with_two_debts(client, headers, tag)

    response = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "17.00", "payment_method": "BANK_QR"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    payments = response.json()["data"]
    # 17.00 splits: 15.00 onto the oldest debt, 2.00 onto the next.
    assert len(payments) == 2
    assert Decimal(payments[0]["amount"]) == Decimal("15.00")
    assert Decimal(payments[1]["amount"]) == Decimal("2.00")

    after = (await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)).json()["data"]
    by_id = {row["id"]: row for row in after}
    assert by_id[debts[0]["id"]]["status"] == "PAID"
    assert Decimal(by_id[debts[1]["id"]]["remaining_amount"]) == Decimal("3.00")

    # The Suppliers list 'Outstanding Debt' follows the same live balances.
    listed = (
        await client.get("/api/v1/suppliers", params={"q": supplier["name"]}, headers=headers)
    ).json()["data"]
    supplier_row = next(row for row in listed if row["id"] == supplier["id"])
    assert supplier_row["debt_balances"] == {"USD": "3.0000"}

    over = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "3.01", "payment_method": "CASH"},
        headers=headers,
    )
    assert over.status_code == 422


@pytest.mark.asyncio
async def test_customer_level_payment_notify_hook_is_awaited(client, monkeypatch, db_session):
    """Regression: the party-payment notify hook used to create coroutines that
    were never awaited. The hook must actually run (it is a safe no-op without
    a Telegram token) once per settled debt, without RuntimeWarnings."""
    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    calls: list[tuple[str, str]] = []

    async def _record(chat_id: str, text: str, **kwargs) -> bool:
        calls.append((chat_id, text))
        return True

    async def _recipients(session):
        return ["12345"]

    monkeypatch.setattr("app.shared.telegram.client.send_message", _record)
    monkeypatch.setattr("app.shared.telegram.service.recipients", _recipients)

    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    customer, _debts, _invoice_nos = await _two_customer_debts(client, headers, tag)

    db_session.add(
        SystemSetting(group_name="telegram", key="telegram.sale_enabled", value={"v": True})
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        json={"amount": "30.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    # Both open debts settled — the notify hook ran for each payment.
    assert len(calls) == 2
    assert all("Debt Payment" in text for _chat, text in calls)

    await db_session.execute(
        delete(SystemSetting).where(SystemSetting.key == "telegram.sale_enabled")
    )
    await db_session.commit()
