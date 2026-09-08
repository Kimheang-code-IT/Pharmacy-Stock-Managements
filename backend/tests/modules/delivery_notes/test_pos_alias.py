"""POS auto-entry delivery note: POST /pos/sales/{id}/delivery-notes.

Prefills one delivery note from a single sale (all remaining undelivered qty
by default; phone/location from the customer), reusing the canonical create
transaction. Delivery notes never mutate stock.
"""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of, make_customer, make_stocked_product
from tests.utils import admin_headers


async def _complete_sale(client, headers, product_id, customer_id, *, quantity="4"):
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "customer_id": customer_id,
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_pos_alias_prefills_note_from_one_sale(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="DNA-1", name="Delivery Alias Widget")
    customer = await make_customer(
        client, headers, code="CUS-DNA-1", name="Delivery Alias Customer"
    )
    sale = await _complete_sale(client, headers, product["id"], customer["id"])

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/delivery-notes",
        json={"delivery_phone": "012345678", "delivery_location": "Street 1, Phnom Penh"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    note = response.json()["data"]

    assert note["delivery_no"].startswith("DN-")
    assert note["status"] == "DRAFT"
    assert note["customer_id"] == customer["id"]
    assert note["sales"] == [{"sale_id": sale["id"], "invoice_no": sale["invoice_no"]}]
    assert note["delivery_phone"] == "012345678"
    assert note["delivery_location"] == "Street 1, Phnom Penh"
    assert len(note["items"]) == 1
    assert Decimal(note["items"][0]["qty_to_deliver"]) == Decimal("4.0000")

    # Delivery notes never mutate stock.
    assert await balance_of(client, headers, product["id"]) == Decimal("6.0000")


@pytest.mark.asyncio
async def test_pos_alias_twice_rejects_nothing_left_to_deliver(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="DNA-2", name="Delivery Alias 2 Widget")
    customer = await make_customer(client, headers, code="CUS-DNA-2", name="Delivery Alias 2 Customer")
    sale = await _complete_sale(client, headers, product["id"], customer["id"])

    first = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/delivery-notes", json={}, headers=headers
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/delivery-notes", json={}, headers=headers
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_pos_alias_requires_delivery_permission(client, db_session):
    from tests.utils import create_user_with_role, login

    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="DNA-3", name="Delivery Alias 3 Widget")
    customer = await make_customer(client, headers, code="CUS-DNA-3", name="Delivery Alias 3 Customer")
    sale = await _complete_sale(client, headers, product["id"], customer["id"])

    await create_user_with_role(
        db_session,
        email="pos-cashier@example.com",
        password="pos-cashier-123",
        role_name="Cashier POS",
        permissions=["dashboard.view", "pos.access", "pos.print"],
    )
    await db_session.commit()
    cashier = await login(client, "pos-cashier@example.com", "pos-cashier-123")
    cashier_headers = {"Authorization": f"Bearer {cashier['access_token']}"}

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/delivery-notes", json={}, headers=cashier_headers
    )
    assert response.status_code == 403, response.text
