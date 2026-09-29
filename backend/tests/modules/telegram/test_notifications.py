"""Telegram notification coverage for the paths the existing suites miss.

`sale`, `purchase`, customer debt payment, daily summary and expiry scans are
covered elsewhere. This file adds: supplier debt payments, Google Sheets backup
results, the expiry alert message text (plain text, no parse_mode), HTML
escaping of dynamic values, multi-recipient fan-out with a failing recipient,
and the Settings test-connection / send-test endpoints.
"""

from decimal import Decimal
from types import SimpleNamespace
import uuid as _uuid

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


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


async def _set_setting(session, key: str, value, *, group: str = "telegram") -> None:
    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    await session.execute(delete(SystemSetting).where(SystemSetting.key == key))
    session.add(SystemSetting(group_name=group, key=key, value={"v": value}))
    await session.commit()


@pytest.fixture
def captured_sends(monkeypatch):
    """Capture every send at the client boundary; one verified recipient."""
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str, **kwargs) -> bool:
        sent.append((chat_id, text))
        return True

    async def fake_recipients(session):
        return ["12345"]

    monkeypatch.setattr("app.shared.telegram.client.send_message", fake_send)
    monkeypatch.setattr("app.shared.telegram.service.recipients", fake_recipients)
    return sent


# --------------------------------------------------------------- supplier payment


async def _supplier_with_debt(client, headers, tag: str):
    supplier = (
        await client.post(
            "/api/v1/suppliers", json={"code": f"TGS-{tag}", "name": f"TG Supplier {tag}"}, headers=headers
        )
    ).json()["data"]
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"TGS-C-{tag}", "name": f"TG Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"TGS-P-{tag}",
                "name": f"TG Pay Product {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "10.00",
            },
            headers=headers,
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
    debts = (await client.get(f"/api/v1/suppliers/{supplier['id']}/debts", headers=headers)).json()["data"]
    assert len(debts) == 1
    return supplier, debts[0]


@pytest.mark.asyncio
async def test_supplier_debt_payment_notification_sent(client, captured_sends, db_session):
    headers = await admin_headers(client)

    tag = _uuid.uuid4().hex[:6]
    supplier, debt = await _supplier_with_debt(client, headers, tag)

    # Supplier debts are the purchase stream → the purchase toggle gates them.
    await _set_setting(db_session, "telegram.purchase_enabled", True)
    captured_sends.clear()  # drop anything from the seeding stock-in

    payment = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "BANK_QR"},
        headers=headers,
    )
    assert payment.status_code == 201, payment.text

    assert len(captured_sends) == 1
    _, text = captured_sends[0]
    assert "Supplier Payment" in text
    assert supplier["name"] in text
    assert "Remaining debt" in text
    # 15.00 outstanding − 5.00 paid = 10.00 remaining.
    assert "10.00" in text


@pytest.mark.asyncio
async def test_supplier_level_payment_notification_sent(client, captured_sends, db_session):
    headers = await admin_headers(client)

    tag = _uuid.uuid4().hex[:6]
    supplier, _debt = await _supplier_with_debt(client, headers, tag)
    await _set_setting(db_session, "telegram.purchase_enabled", True)
    captured_sends.clear()

    response = await client.post(
        f"/api/v1/suppliers/{supplier['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    assert len(captured_sends) == 1
    assert "Supplier Payment" in captured_sends[0][1]


def test_supplier_payment_formatter_fields():
    from app.shared.telegram.service import format_supplier_payment_text

    text = format_supplier_payment_text(
        {
            "document_no": "STI-000009",
            "payment_no": "SDP-000003",
            "supplier": "Angkor Wholesale",
            "currency": "KHR",
            "total": "400000.00",
            "paid": "100000.00",
            "payment_method": "BANK_QR",
            "remaining": "300000.00",
            "cashier": "Sok",
        },
        timezone_name="UTC",
    )
    assert "Supplier Payment" in text
    assert "Document: STI-000009" in text
    assert "Payment No: SDP-000003" in text
    assert "Supplier: Angkor Wholesale" in text
    assert "<b>Paid: \u17db100000.00</b>" in text
    assert "Remaining debt: \u17db300000.00" in text


# ------------------------------------------------------------------- backup


def test_backup_notification_formatter_statuses():
    from app.shared.telegram.service import format_backup_text

    finished = __import__("datetime").datetime(2026, 9, 4, 3, 0, 0)
    job = SimpleNamespace(
        status="partial",
        tables_succeeded=7,
        tables_total=8,
        rows_appended=120,
        rows_updated=4,
        rows_skipped=2,
        tables_failed=1,
        error_message="Sheet 'payments' quota exceeded",
        finished_at=finished,
    )
    text = format_backup_text(job, spreadsheet="X", timezone_name="UTC")
    assert "Google Sheets Backup" in text
    assert "( partial )" in text
    assert "Tables: 7/8" in text
    assert "New rows: 120" in text
    assert "Updated rows: 4" in text
    assert "Skipped: 2" in text
    assert "Failed tables: 1" in text
    assert "quota exceeded" in text

    failed = format_backup_text(SimpleNamespace(status="failed", error_message="boom"), timezone_name="UTC")
    assert "( failed )" in failed
    assert "Tables: 0/0" in failed


@pytest.mark.asyncio
async def test_backup_result_broadcast_fan_out_and_master_gate(db_session, monkeypatch):
    from app.shared.telegram.service import notify_backup_result

    job = SimpleNamespace(
        status="success",
        tables_succeeded=3,
        tables_total=3,
        rows_appended=10,
        rows_updated=0,
        rows_skipped=0,
        tables_failed=0,
        error_message=None,
        finished_at=None,
    )

    async def _no_recipients(session):
        return []

    monkeypatch.setattr("app.shared.telegram.service.recipients", _no_recipients)
    delivered: list[str] = []

    async def _sender(chat_id: str, text: str) -> bool:
        delivered.append(chat_id)
        return True

    # Token absent → master switch off, nothing sent.
    assert await notify_backup_result(db_session, job=job, sender=_sender) == 0
    assert delivered == []

    await _set_setting(db_session, "telegram.bot_token", "test-token")
    await _set_setting(db_session, "telegram.enabled", True)

    # No recipients still delivers to nobody.
    assert await notify_backup_result(db_session, job=job, sender=_sender) == 0

    async def _three_recipients(session):
        return ["1", "2", "3"]

    monkeypatch.setattr("app.shared.telegram.service.recipients", _three_recipients)

    async def _flaky(chat_id: str, text: str) -> bool:
        if chat_id == "2":
            raise RuntimeError("recipient blocked the bot")
        delivered.append(chat_id)
        return True

    # One failing recipient is swallowed; the other two still deliver.
    assert await notify_backup_result(db_session, job=job, sender=_flaky) == 2
    assert set(delivered) == {"1", "3"}


# --------------------------------------------------------------- expiry text


def test_expiry_alert_text_branches_and_is_plain_text():
    from app.modules.telegram.service import format_expiry_alert_text

    lot = {
        "product_name": "Amoxicillin",
        "barcode": "885000000001",
        "batch_no": "BATCH-001",
        "expiry_date": "2026-10-01",
        "remaining_qty": Decimal("12.0000"),
    }
    early = format_expiry_alert_text(lot, alert_level=1, days_until_expiry=60)
    assert "Product Expiry Alert 01" in early
    assert "Product: Amoxicillin" in early
    assert "Barcode: 885000000001" in early
    assert "Batch: BATCH-001" in early
    assert "Days remaining: 60" in early
    # Expiry alerts are plain text — no HTML tags, no forced bold.
    assert "<b>" not in early

    assert "expires TODAY" in format_expiry_alert_text(lot, alert_level=2, days_until_expiry=0)
    assert "EXPIRED 3 day(s) ago" in format_expiry_alert_text(lot, alert_level=2, days_until_expiry=-3)


@pytest.mark.asyncio
async def test_expiry_default_sender_is_plain_text(monkeypatch):
    from app.modules.telegram.service import _default_sender

    calls: list[dict] = []

    async def fake_send(chat_id: str, text: str, **kwargs) -> bool:
        calls.append({"chat_id": chat_id, "text": text, **kwargs})
        return True

    monkeypatch.setattr("app.shared.telegram.client.send_message", fake_send)
    assert await _default_sender("999", "alert") is True
    assert calls[0]["chat_id"] == "999"
    assert "parse_mode" not in calls[0]


# ------------------------------------------------------------------- escaping


def test_sale_formatter_escapes_dynamic_html():
    from app.shared.telegram.service import format_sale_text

    text = format_sale_text(
        {
            "invoice_no": "INV-<1>",
            "occurred_at": "2026-09-04T12:00:00+00:00",
            "customer": "A & B <b>Co</b>",
            "currency": "USD",
            "subtotal": "10.00",
            "discount": "0.00",
            "delivery_price": "0.00",
            "total": "10.00",
            "paid": "10.00",
            "payment_method": "CASH",
            "debt": "0.00",
            "cashier": "Sok",
            "items": [{"name": "Amp & <script>", "quantity": "1", "uom": "pc", "unit_price": "10.00", "line_total": "10.00"}],
        }
    )
    # Dynamic values are HTML-escaped so they cannot inject markup.
    assert "A &amp; B &lt;b&gt;Co&lt;/b&gt;" in text
    assert "Amp &amp; &lt;script&gt;" in text
    assert "<script>" not in text
    # The card's own bold markup survives.
    assert "<b>Total: $10.00</b>" in text


# --------------------------------------------------- settings test endpoints


@pytest.mark.asyncio
async def test_settings_telegram_test_connection_and_destination(client, captured_sends, db_session):
    headers = await admin_headers(client)

    # No token saved → disabled status, nothing sent.
    disabled = await client.post("/api/v1/settings/app-config/telegram/test-connection", headers=headers)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"

    await _set_setting(db_session, "telegram.bot_token", "test-token")
    await _set_setting(db_session, "telegram.enabled", True)

    connected = await client.post("/api/v1/settings/app-config/telegram/test-connection", headers=headers)
    assert connected.status_code == 200, connected.text
    assert connected.json()["data"]["status"] == "connected"
    assert captured_sends and "Test Notification" in captured_sends[-1][1]

    # Explicit destination bypasses recipient lookup.
    captured_sends.clear()
    direct = await client.post(
        "/api/v1/settings/app-config/telegram/send-test",
        json={"destinationId": "555"},
        headers=headers,
    )
    assert direct.status_code == 200, direct.text
    assert direct.json()["data"]["status"] == "connected"
    assert captured_sends and captured_sends[-1][0] == "555"
