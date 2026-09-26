"""Canonical Telegram notifications — sale, purchase, payment, daily summary.

The canonical service lives in `app.shared.telegram.service`. Every send is
settings-gated, post-commit, best-effort (never rolls back the business
transaction) and text-only — no invoice files/PDFs are ever sent.
"""

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers

ADMIN_NAME = "System Administrator"


@pytest.fixture(autouse=True)
async def _reset_telegram_settings(db_session):
    """Remove telegram toggles before/after each test so they never leak."""
    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    yield
    await db_session.execute(
        delete(SystemSetting).where(SystemSetting.group_name == "telegram")
    )
    await db_session.commit()


@pytest.fixture
def captured_sends(monkeypatch):
    """Capture every Telegram broadcast at the client boundary."""
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str, **kwargs) -> bool:
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr("app.shared.telegram.client.send_message", fake_send)
    # One verified recipient so broadcasts actually reach the sender.
    async def fake_recipients(session):
        return ["12345"]

    monkeypatch.setattr("app.shared.telegram.service.recipients", fake_recipients)
    return sent


async def _enable(session, key: str, value=True) -> None:
    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    await session.execute(delete(SystemSetting).where(SystemSetting.key == f"telegram.{key}"))
    session.add(SystemSetting(group_name="telegram", key=f"telegram.{key}", value={"v": value}))
    await session.commit()


async def _cash_sale(client, headers, product_id, *, method="CASH"):
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": method,
            "amount_received": "100.00",
            "items": [{"product_id": product_id, "quantity": "2"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_sale_notification_sent_after_commit(client, captured_sends, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-1", name="Notify Widget")
    await _enable(db_session, "sale_enabled")

    sale = await _cash_sale(client, headers, product["id"], method="CASH")

    assert len(captured_sends) == 1
    chat_id, text = captured_sends[0]
    assert chat_id == "12345"
    assert sale["invoice_no"] in text
    # Receipt-style card: emoji + bold title, products section, HTML parse mode.
    assert "New Checkout Completed" in text
    assert text.startswith("\U0001f9fe")
    assert "Products:" in text
    assert "Notify Widget" in text
    # No invoice files/PDFs — text only.
    assert ".pdf" not in text.lower()


@pytest.mark.asyncio
async def test_sale_notification_disabled_by_default(client, captured_sends):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-2", name="Quiet Widget")

    await _cash_sale(client, headers, product["id"], method="CASH")

    assert captured_sends == []


@pytest.mark.asyncio
async def test_sale_notification_toggle_respected(client, captured_sends, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-3", name="Toggled Widget")
    await _enable(db_session, "sale_enabled", False)

    await _cash_sale(client, headers, product["id"])
    assert captured_sends == []


@pytest.mark.asyncio
async def test_khr_sale_notification_keeps_currency(client, captured_sends, db_session):
    """KHR sale notification shows the currency + rate, never mixed with USD."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-K", name="KHR Widget")
    await _enable(db_session, "sale_enabled")

    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100000",
            "currency": "KHR",
            "exchange_rate": "4100",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text

    assert len(captured_sends) == 1
    _, text = captured_sends[0]
    # KHR amounts keep their own currency symbol — never shown as USD.
    assert "\u17db" in text
    assert "$" not in text


@pytest.mark.asyncio
async def test_debt_sale_does_not_notify(client, captured_sends, db_session):
    """Debt sales notify through customer debt payments instead (spec §3.6.2)."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-4", name="Debt Notify Widget")
    customer = await make_customer(client, headers, code="TG-C-1", name="TG Customer")
    await _enable(db_session, "sale_enabled")

    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "5.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert captured_sends == []


@pytest.mark.asyncio
async def test_purchase_notification_sent(client, captured_sends, db_session):
    """Stock In notification is settings-gated and post-commit."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-5", name="Purchase Widget")
    await _enable(db_session, "purchase_enabled")
    captured_sends.clear()  # make_stocked_product itself performs a stock-in

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "5",
                    "unit_cost": "2.00",
                    "line_total": "10.00",
                }
            ],
            "paid_amount": "10.00",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    document_no = response.json()["data"]["document_no"]

    assert len(captured_sends) == 1
    _, text = captured_sends[0]
    assert "Stock In Received" in text
    assert document_no in text
    assert "Purchase Widget" in text


@pytest.mark.asyncio
async def test_debt_payment_notification_sent(client, captured_sends, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-6", name="Debt Pay Widget")
    customer = await make_customer(client, headers, code="TG-C-2", name="TG Payer")
    await _enable(db_session, "sale_enabled")

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
    assert captured_sends == []  # sale itself: no notify (debt sale)
    debt_sale = sale.json()["data"]

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]

    payment = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "7.00", "payment_method": "BANK_QR"},
        headers=headers,
    )
    assert payment.status_code == 201, payment.text

    assert len(captured_sends) == 1
    _, text = captured_sends[0]
    assert debt_sale["invoice_no"] in text
    assert "Debt Payment" in text
    assert "CDP-" in text


@pytest.mark.asyncio
async def test_sale_commits_even_when_telegram_down(client, monkeypatch, db_session):
    """Telegram failure NEVER rolls back the committed sale."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-7", name="Resilient Widget")
    await _enable(db_session, "sale_enabled")

    async def broken_send(chat_id: str, text: str) -> bool:
        raise RuntimeError("telegram down")

    monkeypatch.setattr("app.shared.telegram.client.send_message", broken_send)

    sale = await _cash_sale(client, headers, product["id"], method="CASH")

    detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["payment_status"] == "PAID"


# ------------------------------------------------------------------ summaries


@pytest.mark.asyncio
async def test_daily_summary_totals_never_mix_currencies(client, captured_sends, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-S1", name="Summary Widget")
    customer = await make_customer(client, headers, code="TG-S-C", name="Summary Customer")

    # One USD cash sale and one KHR debt sale on "today".
    usd = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "30.00",
            "items": [{"product_id": product["id"], "quantity": "3"}],
        },
        headers=headers,
    )
    assert usd.status_code == 201, usd.text
    khr = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "currency": "KHR",
            "exchange_rate": "4100",
            "amount_received": "0",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert khr.status_code == 201, khr.text

    from app.core.database import SessionFactory
    from app.shared.telegram.service import daily_summary_totals

    async with SessionFactory() as session:
        summary = await daily_summary_totals(session, day=datetime.now(timezone.utc).date())

    assert summary["sales"]["USD"]["count"] >= 1
    assert Decimal(summary["sales"]["USD"]["total"]) >= Decimal("15.00")
    assert summary["sales"]["KHR"]["count"] >= 1
    assert summary["customer_debt_total"]  # KHR debt recorded separately
    # The summary dict keeps per-currency buckets; no combined USD+KHR field exists.
    assert "total" not in summary["sales"]


@pytest.mark.asyncio
async def test_daily_summary_format_separates_currencies():
    from app.shared.telegram.service import format_daily_summary_text

    text = format_daily_summary_text(
        {
            "day": "2026-09-10",
            "sales": {
                "USD": {"count": 3, "total": "45.00"},
                "KHR": {"count": 2, "total": "82000.00"},
            },
            "purchases": {"USD": {"count": 1, "total": "100.00"}},
            "customer_debt_total": "12.00",
            "supplier_debt_total": "0.00",
            "delivered_count": 4,
            "pending_delivery_count": 2,
            "out_of_stock_count": 1,
        }
    )
    assert "Daily Summary" in text
    assert "Sales: 5" in text
    assert "USD Sales: $45.00" in text
    assert "KHR Sales: \u17db82000.00" in text
    assert "Purchases: 1" in text
    assert "USD Purchases: $100.00" in text
    assert "Customer debt outstanding: $12.00" in text
    assert "Pending deliveries: 2" in text
    assert "Out-of-stock products: 1" in text
    # Never a blind USD+KHR sum.
    assert "82045" not in text


@pytest.mark.asyncio
async def test_daily_summary_send_gated_and_delivered(client, captured_sends, db_session):
    from app.core.database import SessionFactory
    from app.shared.telegram.service import send_daily_summary

    # No bot token saved in Settings yet -> master switch reports disabled.
    async with SessionFactory() as session:
        result = await send_daily_summary(session, day=datetime.now(timezone.utc).date())
    assert result == {"enabled": False, "sent": 0}

    await _enable(db_session, "bot_token", "test-token")
    await _enable(db_session, "daily_summary_enabled")
    async with SessionFactory() as session:
        result = await send_daily_summary(session, day=datetime.now(timezone.utc).date())
    assert result["enabled"] is True
    assert result["sent"] == 1
    assert "Daily Summary" in captured_sends[0][1]


@pytest.mark.asyncio
async def test_test_notification_endpoint(client, captured_sends, db_session):
    headers = await admin_headers(client)

    # Disabled by default → soft "enabled: False" result, nothing sent.
    response = await client.post("/api/v1/admin/settings/telegram-test", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["enabled"] is False
    assert captured_sends == []

    # A token saved in Settings (DB) flips the master switch on.
    await _enable(db_session, "bot_token", "test-token")
    await _enable(db_session, "enabled")
    response = await client.post("/api/v1/admin/settings/telegram-test", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["enabled"] is True
    assert data["sent"] == 1
    assert "Test Notification" in captured_sends[0][1]


# ------------------------------------------------------------------ formatters


def test_sale_formatter_renders_fields_in_app_timezone():
    from app.shared.telegram.service import format_sale_text

    text = format_sale_text(
        {
            "invoice_no": "INV-000001",
            "occurred_at": "2026-09-04T12:00:00+00:00",
            "customer": "Dara",
            "currency": "USD",
            "exchange_rate": "1",
            "item_count": 3,
            "subtotal": "30.00",
            "discount": "1.00",
            "delivery_price": "0.00",
            "total": "29.00",
            "paid": "29.00",
            "payment_method": "CASH",
            "debt": "0.00",
            "cashier": "Sok",
        },
        timezone_name="Asia/Phnom_Penh",
    )
    assert "New Checkout Completed" in text
    assert "Invoice ID: INV-000001" in text
    assert "Date: 2026-09-04 19:00:00" in text  # UTC+07 conversion
    assert "Customer: Dara" in text
    assert "<b>Total: $29.00</b>" in text
    assert "Paid: $29.00" in text
    assert "Payment: Cash" in text
    assert "By: Sok" in text


def test_purchase_formatter_renders_fields():
    from app.shared.telegram.service import format_purchase_text

    text = format_purchase_text(
        {
            "document_no": "STI-000001",
            "occurred_at": "2026-09-04T03:00:00+00:00",
            "supplier": "Angkor Wholesale",
            "currency": "KHR",
            "exchange_rate": "4100",
            "item_count": 4,
            "subtotal": "410000.00",
            "discount": "10000.00",
            "tax": "0.00",
            "total": "400000.00",
            "paid": "400000.00",
            "debt": "0.00",
            "user": "Sok",
        },
        timezone_name="Asia/Phnom_Penh",
    )
    assert "Stock In Received" in text
    assert "Purchase: STI-000001" in text
    assert "Supplier: Angkor Wholesale" in text
    assert "<b>Total: \u17db400000.00</b>" in text
    assert "By: Sok" in text


def test_formatters_render_khmer_labels_and_products():
    """The Settings notification language switches every card to Khmer."""
    from app.shared.telegram.service import format_sale_text

    text = format_sale_text(
        {
            "invoice_no": "INV-000009",
            "occurred_at": "2026-09-04T12:00:00+00:00",
            "customer": None,
            "currency": "USD",
            "subtotal": "10.00",
            "discount": "0.00",
            "delivery_price": "0.00",
            "total": "10.00",
            "paid": "10.00",
            "payment_method": "CASH",
            "debt": "0.00",
            "cashier": "Sok",
            "items": [
                {"name": "Paracetamol", "quantity": "2.0000", "uom": "pcs", "unit_price": "5.00", "line_total": "10.00"}
            ],
        },
        lang="km",
    )
    # Title, walk-in label and Products heading are in Khmer.
    assert "\u1780\u17b6\u179a\u179b\u1780\u17cb\u1794\u17b6\u1793\u179f\u1798\u17d2\u179a\u17c1\u1785" in text
    assert "\u17a2\u178f\u17b7\u1790\u17b7\u1787\u1793\u1791\u17bc\u1791\u17c5" in text
    assert "\u1791\u17c6\u1793\u17b7\u1789:" in text
    # Decimals are trimmed in product rows.
    assert "Paracetamol 2 pcs x $5.00 = $10.00" in text