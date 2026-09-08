"""Telegram payment/invoice text notifications — spec sections 3.6 + 3.6.2."""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers

ADMIN_NAME = "System Administrator"


@pytest.fixture
def captured_notify(monkeypatch):
    payloads: list[dict] = []

    def fake_queue(payload: dict) -> bool:
        payloads.append(payload)
        return True

    monkeypatch.setattr("app.shared.telegram.queue_payment_invoice_notify", fake_queue)
    return payloads


@pytest.fixture
def raising_notify(monkeypatch):
    def broken_queue(payload: dict) -> bool:
        raise RuntimeError("broker down")

    monkeypatch.setattr("app.shared.telegram.queue_payment_invoice_notify", broken_queue)
    return broken_queue


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
async def test_cash_sale_enqueues_invoice_notify(client, captured_notify):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-1", name="Notify Widget")

    sale = await _cash_sale(client, headers, product["id"], method="CASH")

    assert len(captured_notify) == 1
    payload = captured_notify[0]
    assert payload["kind"] == "SALE"
    assert payload["invoice_no"] == sale["invoice_no"]
    assert Decimal(payload["total"]) == Decimal("20.00")
    assert Decimal(payload["paid"]) == Decimal("20.00")
    assert Decimal(payload["remaining"]) == Decimal("0.00")
    assert payload["payment_method"] == "CASH"
    assert payload["item_count"] == 1
    assert payload["cashier"] == ADMIN_NAME
    assert "occurred_at" in payload


@pytest.mark.asyncio
async def test_bank_qr_sale_enqueues_notify(client, captured_notify):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-2", name="QR Notify Widget")

    await _cash_sale(client, headers, product["id"], method="BANK_QR")

    assert len(captured_notify) == 1
    assert captured_notify[0]["payment_method"] == "BANK_QR"


@pytest.mark.asyncio
async def test_debt_sale_does_not_notify(client, captured_notify):
    """Debt sales notify through customer debt payments instead (spec 3.6.2)."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-3", name="Debt Notify Widget")
    customer = await make_customer(client, headers, code="TG-C-1", name="TG Customer")

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
    assert captured_notify == []


@pytest.mark.asyncio
async def test_notify_skipped_when_disabled(client, captured_notify, db_session):
    headers = await admin_headers(client)
    from sqlalchemy import delete

    from app.modules.administration.models import SystemSetting

    db_session.add(
        SystemSetting(
            group_name="telegram",
            key="telegram.payment_invoice_notify_enabled",
            value={"v": False},
        )
    )
    await db_session.commit()
    product = await make_stocked_product(client, headers, sku="TG-4", name="Disabled Notify Widget")

    await _cash_sale(client, headers, product["id"])
    assert captured_notify == []

    # Restore the default so later tests in this session see the enabled default.
    await db_session.execute(
        delete(SystemSetting).where(
            SystemSetting.key == "telegram.payment_invoice_notify_enabled"
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_debt_payment_enqueues_notify(client, captured_notify):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-5", name="Debt Pay Notify Widget")
    customer = await make_customer(client, headers, code="TG-C-2", name="TG Payer")

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
    assert captured_notify == []  # sale itself: no notify (debt sale)
    debt_sale = sale.json()["data"]

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]

    payment = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "7.00", "payment_method": "BANK_QR"},
        headers=headers,
    )
    assert payment.status_code == 201, payment.text

    assert len(captured_notify) == 1
    payload = captured_notify[0]
    assert payload["kind"] == "DEBT_PAYMENT"
    assert payload["invoice_no"] == debt_sale["invoice_no"]
    assert payload["payment_no"].startswith("CDP-")
    assert Decimal(payload["paid"]) == Decimal("7.00")
    assert Decimal(payload["remaining"]) == Decimal("8.00")
    assert payload["payment_method"] == "BANK_QR"
    assert payload["cashier"] == ADMIN_NAME


@pytest.mark.asyncio
async def test_sale_commits_even_when_notify_enqueue_fails(client, raising_notify):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="TG-6", name="Resilient Widget")

    sale = await _cash_sale(client, headers, product["id"], method="CASH")

    # The sale is committed and fully retrievable despite the enqueue failure.
    detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["payment_status"] == "PAID"


# ----------------------------------------------------------------- formatter


def test_formatter_renders_sale_fields_in_app_timezone():
    from app.shared.telegram.notify import format_payment_invoice_text

    text = format_payment_invoice_text(
        {
            "kind": "SALE",
            "invoice_no": "INV-000001",
            "occurred_at": "2026-09-04T12:00:00+00:00",
            "customer": "Dara",
            "item_count": 3,
            "subtotal": "30.00",
            "discount": "1.00",
            "total": "29.00",
            "paid": "29.00",
            "payment_method": "CASH",
            "remaining": "0.00",
            "cashier": "Sok",
        },
        shop_name="My Shop",
        timezone_name="Asia/Phnom_Penh",
    )
    assert text.splitlines()[0] == "My Shop"
    assert "Invoice: INV-000001" in text
    assert "Date: 2026-09-04 19:00:00" in text  # UTC+07 conversion
    assert "Customer: Dara" in text
    assert "Items: 3" in text
    assert "Subtotal: 30.00" in text
    assert "Discount: 1.00" in text
    assert "Total: 29.00" in text
    assert "Paid: 29.00" in text
    assert "Method: CASH" in text
    assert "Remaining debt: 0.00" in text
    assert "Cashier: Sok" in text


def test_formatter_renders_debt_payment_and_falls_back_to_utc():
    from app.shared.telegram.notify import format_payment_invoice_text

    text = format_payment_invoice_text(
        {
            "kind": "DEBT_PAYMENT",
            "invoice_no": "INV-000002",
            "payment_no": "CDP-000001",
            "occurred_at": "not-a-date",
            "customer": "TG Payer",
            "total": "20.00",
            "paid": "7.00",
            "payment_method": "BANK_QR",
            "remaining": "13.00",
            "cashier": "Sok",
            "bot_token": "SECRET-TOKEN",  # unknown/secret keys must be ignored
        },
        shop_name="My Shop",
        timezone_name="Not/AZone",
    )
    assert "Payment: CDP-000001" in text
    assert "Total: 20.00" in text
    assert "Paid: 7.00" in text
    assert "Remaining debt: 13.00" in text
    assert "SECRET-TOKEN" not in text
    assert "Items:" not in text  # not part of a debt payment payload
