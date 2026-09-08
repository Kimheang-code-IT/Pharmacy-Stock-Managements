"""Delivery Notes — /status Update Status endpoint + camelCase create body (§5.13).

The unified POST /delivery-notes/{id}/status enforces the §2.1.9 transition
table, per-target permissions and the cancel reason requirement. Legacy verb
aliases (confirm / deliver / cancel) map onto the same transition service.
"""

import uuid
from decimal import Decimal

import pytest

from tests.modules.delivery_notes.test_delivery_notes import _sale_two_lines
from tests.utils import admin_headers, create_user_with_role, login


@pytest.mark.asyncio
async def test_create_accepts_camel_case_body(client):
    """The UI posts {lines:[{saleId, saleItemId, qtyToDeliver}]} — same note."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product_a, product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)

    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "confirm": False,
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": 3}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()["data"]
    assert note["invoice_nos"] == [sale["invoice_no"]]
    assert Decimal(note["items"][0]["qty_to_deliver"]) == Decimal("3.0000")


@pytest.mark.asyncio
async def test_status_transitions_follow_the_allowed_table(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)

    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": 5}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["data"]["id"]

    # Draft → Delivered is NOT a legal transition (§2.1.9 table).
    jump = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "DELIVERED"}, headers=headers
    )
    assert jump.status_code == 409

    confirm = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "CONFIRMED"}, headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["data"]["status"] == "CONFIRMED"

    # Confirmed → Delivered is legal (Delivery OK shortcut).
    early_deliver = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "DELIVERED"}, headers=headers
    )
    assert early_deliver.status_code == 200, early_deliver.text
    body = early_deliver.json()["data"]
    assert body["status"] == "DELIVERED"
    assert body["delivered_at"]
    assert all(Decimal(item["qty_delivered"]) == Decimal("5.0000") for item in body["items"])

    # Delivered is terminal — no further transitions.
    late_cancel = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status",
        json={"status": "CANCELLED", "cancel_reason": "wrong address"},
        headers=headers,
    )
    assert late_cancel.status_code == 409


@pytest.mark.asyncio
async def test_status_out_for_delivery_path_and_audit(client, db_session):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)

    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": 1}],
        },
        headers=headers,
    )
    note_id = created.json()["data"]["id"]

    confirmed = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "CONFIRMED"}, headers=headers
    )
    assert confirmed.status_code == 200

    out = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "OUT_FOR_DELIVERY"}, headers=headers
    )
    assert out.status_code == 200, out.text
    assert out.json()["data"]["status"] == "OUT_FOR_DELIVERY"

    delivered = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "DELIVERED"}, headers=headers
    )
    assert delivered.status_code == 200
    assert delivered.json()["data"]["delivered_at"] is not None

    # Every status change is audited.
    audits = await client.get(
        "/api/v1/admin/audit-logs", params={"module": "delivery", "limit": 100}, headers=headers
    )
    assert audits.status_code == 200
    actions = {row["action"] for row in audits.json()["data"]}
    assert {"delivery_confirmed", "delivery_out_for_delivery", "delivery_delivered"} <= actions


@pytest.mark.asyncio
async def test_status_cancel_requires_reason(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)
    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": 1}],
        },
        headers=headers,
    )
    note_id = created.json()["data"]["id"]

    missing_reason = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "CANCELLED"}, headers=headers
    )
    assert missing_reason.status_code == 422

    confirmed = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "CONFIRMED"}, headers=headers
    )
    assert confirmed.status_code == 200

    cancelled = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status",
        json={"status": "CANCELLED", "cancel_reason": "customer moved"},
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert cancelled.json()["data"]["cancel_reason"] == "customer moved"

    # Cancelled is terminal.
    reopen = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"status": "CONFIRMED"}, headers=headers
    )
    assert reopen.status_code == 409


@pytest.mark.asyncio
async def test_status_legacy_action_aliases_and_permissions(client, db_session):
    """Legacy verb aliases map onto the same transition service + permissions."""
    await create_user_with_role(
        db_session,
        email="dn-status@example.com",
        password="dnstatus1",
        role_name="DN Status Viewer",
        permissions=["delivery.view"],
    )
    await db_session.commit()
    data = await login(client, "dn-status@example.com", "dnstatus1")
    viewer = {"Authorization": f"Bearer {data['access_token']}"}

    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)
    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": 1}],
        },
        headers=headers,
    )
    note_id = created.json()["data"]["id"]

    # Viewer lacks delivery.confirm → legacy alias still rejected.
    forbidden = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"action": "confirm"}, headers=viewer
    )
    assert forbidden.status_code == 403

    confirm = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"action": "confirm"}, headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["data"]["status"] == "CONFIRMED"

    # Confirming an already-confirmed note is an illegal transition.
    again = await client.post(
        f"/api/v1/delivery-notes/{note_id}/status", json={"action": "confirm"}, headers=headers
    )
    assert again.status_code == 409
