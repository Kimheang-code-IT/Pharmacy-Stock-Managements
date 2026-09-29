from sqlalchemy import delete, func, select

from app.modules.customers.models import Customer
from app.modules.customers.service import ensure_walk_in_customer
from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers, deactivate_then_delete


async def test_ensure_walk_in_customer_bootstraps_and_is_idempotent(db_session):
    """Initial setup and data reset rely on this helper so exactly one system
    walk-in customer exists (POS resolves anonymous cash sales to it)."""
    await db_session.execute(delete(Customer).where(Customer.is_walk_in.is_(True)))
    await db_session.flush()

    created = await ensure_walk_in_customer(db_session)
    assert created.is_walk_in is True
    assert created.name == "Walk-in Customer"
    assert created.code.startswith("CUS-")
    await db_session.commit()

    again = await ensure_walk_in_customer(db_session)
    assert again.id == created.id

    count = (
        await db_session.execute(
            select(func.count()).select_from(Customer).where(Customer.is_walk_in.is_(True))
        )
    ).scalar_one()
    assert count == 1


async def test_customer_crud_auto_code_and_walkin_protection(client):
    headers = await admin_headers(client)

    listing = await client.get("/api/v1/customers?q=walk-in", headers=headers)
    assert listing.status_code == 200
    walk_in = next(
        (c for c in listing.json()["data"] if c["is_walk_in"]), None
    ) or (await client.get("/api/v1/customers?q=Walk", headers=headers)).json()["data"][0]
    assert walk_in["is_walk_in"] is True

    patch_walk_in = await client.patch(
        f"/api/v1/customers/{walk_in['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patch_walk_in.status_code == 409

    delete_walk_in = await client.delete(f"/api/v1/customers/{walk_in['id']}", headers=headers)
    assert delete_walk_in.status_code == 409

    created = await client.post(
        "/api/v1/customers",
        json={"name": "Sok Dara", "phone": "098765432", "location": "Phnom Penh, Toul Kork"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    customer = created.json()["data"]
    assert customer["code"].startswith("CUS-")
    assert customer["is_walk_in"] is False
    assert customer["location"] == "Phnom Penh, Toul Kork"

    patched = await client.patch(f"/api/v1/customers/{customer['id']}", json={"note": "VIP"}, headers=headers)
    assert patched.status_code == 200

    deleted = await deactivate_then_delete(client, headers, f"/api/v1/customers/{customer['id']}")
    assert deleted.status_code == 200


async def test_customer_delete_blocked_by_sale_history_then_deactivate(client):
    """A customer with sales history must not be hard-deleted; deactivate instead."""
    headers = await admin_headers(client)

    customer = await make_customer(client, headers, code="CUS-HIST", name="History Customer")
    product = await make_stocked_product(
        client, headers, sku="CUSH-1", name="Customer History Product", qty="10"
    )
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": "0.00",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    blocked = await client.delete(f"/api/v1/customers/{customer['id']}", headers=headers)
    assert blocked.status_code == 409
    assert "deactivate" in blocked.json()["detail"]["message"].lower()

    deactivated = await client.patch(
        f"/api/v1/customers/{customer['id']}", json={"status": "INACTIVE"}, headers=headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["status"] == "INACTIVE"
