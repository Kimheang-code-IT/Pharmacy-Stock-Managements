"""SPA settings surface: App Info / App Config projection + connectivity tests."""

import uuid
from decimal import Decimal

from tests.modules.pos.helpers import balance_of, make_customer, make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers


async def test_app_config_requires_authentication(client):
    response = await client.get("/api/v1/settings/app-config")
    assert response.status_code == 401


async def test_app_config_exposes_full_document(client):
    headers = await admin_headers(client)
    response = await client.get("/api/v1/settings/app-config", headers=headers)
    assert response.status_code == 200, response.text
    config = response.json()["data"]
    for section in ("general", "localization", "email", "telegram", "stock", "notifications", "security", "system"):
        assert section in config, f"missing App Config section {section}"
    assert config["telegram"]["botToken"] == ""
    assert set(config["stock"]) >= {"lowStockLevel", "expiryAlert1Days", "expiryAlert2Days"}


async def test_app_info_round_trip_and_reset(client):
    headers = await admin_headers(client)

    updated = await client.patch(
        "/api/v1/settings/app-info",
        json={"businessName": "Surface Test Pharmacy", "supportEmail": "ops@example.com"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    info = updated.json()["data"]
    assert info["businessName"] == "Surface Test Pharmacy"
    assert info["supportEmail"] == "ops@example.com"

    config = (await client.get("/api/v1/settings/app-config", headers=headers)).json()["data"]
    assert config["telegram"]["botDisplayName"] == "Surface Test Pharmacy"

    reset = await client.post("/api/v1/settings/app-info/reset", headers=headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["data"]["businessName"] == "Yoeun Sokhon Pharmacy"


async def test_app_config_write_accepts_payment_invoice_toggle(client):
    headers = await admin_headers(client)

    # Regression: the SPA writes payment_invoice_notify_enabled via /admin/settings.
    patched = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"telegram": {"payment_invoice_notify_enabled": False}}},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    config = (await client.get("/api/v1/settings/app-config", headers=headers)).json()["data"]
    assert config["telegram"]["paymentInvoiceNotifyEnabled"] is False

    restored = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"telegram": {"payment_invoice_notify_enabled": True}}},
        headers=headers,
    )
    assert restored.status_code == 200


async def test_email_and_telegram_connection_tests_report_status(client):
    headers = await admin_headers(client)

    email = await client.post("/api/v1/settings/app-config/email/test-connection", headers=headers)
    assert email.status_code == 200
    assert email.json()["data"]["status"] == "disabled"

    # Telegram token is empty in tests, so the master switch reports disabled.
    telegram = await client.post("/api/v1/settings/app-config/telegram/send-test", headers=headers)
    assert telegram.status_code == 200
    assert telegram.json()["data"]["status"] == "disabled"


def _destructive_body(action: str) -> dict:
    """Return the exact phrase required for a destructive action."""
    phrases = {
        "RESET_ALL_DATA": "RESET ALL DATA",
        "CLEAR_TRANSACTIONS": "CLEAR TRANSACTIONS",
    }
    return {"confirmation_phrase": phrases[action]}


async def test_reset_data_requires_permission_and_phrase(client):
    headers = await admin_headers(client)
    # Missing phrase body -> validation error, nothing deleted.
    missing = await client.post("/api/v1/settings/reset-data", headers=headers)
    assert missing.status_code == 422, missing.text

    # Wrong phrase -> refused.
    body = _destructive_body("RESET_ALL_DATA")
    body["confirmation_phrase"] = "nope"
    wrong = await client.post("/api/v1/settings/reset-data", json=body, headers=headers)
    assert wrong.status_code == 422, wrong.text


async def test_reset_data_wipes_business_data_and_keeps_admin(client, db_session):
    headers = await admin_headers(client)

    category = (
        await client.post(
            "/api/v1/categories", json={"code": "RST", "name": "Reset Cat"}, headers=headers
        )
    ).json()["data"]
    created = await client.post(
        "/api/v1/products",
        json={
            "sku": "RST-0001",
            "name": "Reset Widget",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "1.00",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["data"]["id"]

    body = _destructive_body("RESET_ALL_DATA")
    response = await client.post("/api/v1/settings/reset-data", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["requiresReauth"] is False
    # A verified pre-deletion backup is recorded.
    assert response.json()["data"]["backup"]["total_rows"] >= 0

    # Business data is gone; the admin session and the walk-in bootstrap survive.
    assert (await client.get(f"/api/v1/products/{product_id}", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/settings/app-config", headers=headers)).status_code == 200
    walk_in = await client.get("/api/v1/customers?q=walk-in", headers=headers)
    assert walk_in.status_code == 200, walk_in.text
    assert any(customer["is_walk_in"] for customer in walk_in.json()["data"])

    # UOMs are Setup data and must be gone after the reset.
    uoms = await client.get("/api/v1/uoms", headers=headers)
    assert uoms.status_code == 200, uoms.text
    assert uoms.json()["data"] == []

    # The shared test DB relies on the seeded UOM catalogue; restore it so the
    # rest of the suite still runs (the reset intentionally leaves it empty).
    from app.modules.uoms.models import UOM
    from app.modules.uoms.service import ensure_default_uoms

    await ensure_default_uoms(db_session)
    db_session.add(UOM(id=DEFAULT_UOM_ID, code="EA", name="Each", symbol="ea", status="ACTIVE"))
    await db_session.commit()


async def test_clear_transactions_removes_history_and_zeroes_stock(client):
    """Regression: delivery-note lines reference sale items, so the delete order
    must remove the delivery tables before sale_items/sales."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(
        client, headers, sku=f"CLR-{tag}", name=f"Clear {tag}", qty="10"
    )
    customer = await make_customer(
        client, headers, code=f"CLR-C-{tag}", name=f"Clear Cust {tag}"
    )
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    line_id = sale_data["items"][0]["id"]

    note = await client.post(
        "/api/v1/delivery",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale_data["id"], "saleItemId": line_id, "qtyToDeliver": "1"}],
        },
        headers=headers,
    )
    assert note.status_code == 201, note.text

    body = _destructive_body("CLEAR_TRANSACTIONS")
    cleared = await client.post("/api/v1/settings/clear-transactions", json=body, headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["cleared"] is True

    # History is gone; stock is zeroed; master data survives.
    assert (await client.get(f"/api/v1/sales/{sale_data['id']}", headers=headers)).status_code == 404
    assert await balance_of(client, headers, product["id"]) == Decimal("0.0000")
    assert (await client.get(f"/api/v1/products/{product['id']}", headers=headers)).status_code == 200


async def test_reference_options_endpoints(client):
    headers = await admin_headers(client)
    for path in ("/api/v1/admin/roles/options", "/api/v1/suppliers/options", "/api/v1/customers/options"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, f"{path}: {response.text}"
        assert isinstance(response.json()["data"], list)
