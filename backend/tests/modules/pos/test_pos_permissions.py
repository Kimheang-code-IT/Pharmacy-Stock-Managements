"""POS permission enforcement (spec section 2.1.8).

Every POS operation is gated in the BACKEND, not only in frontend buttons.
Missing permissions return HTTP 403 (never 409), and the Administrator wildcard
(`ALL_PAGES`) retains full access.
"""

import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers, create_user_with_role, login


async def _limited_headers(db_session, client, permissions: list[str], suffix: str) -> dict:
    email = f"pos-{suffix}-{uuid.uuid4().hex[:8]}@example.com"
    password = "limitedpass1"
    await create_user_with_role(
        db_session,
        email=email,
        password=password,
        role_name=f"POS {suffix} {uuid.uuid4().hex[:6]}",
        permissions=permissions,
    )
    await db_session.commit()
    data = await login(client, email, password)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _cash_sale(client, headers, product_id, quantity="2") -> dict:
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_debt_sale_requires_pos_debt_sale(client, db_session):
    """pos.access alone cannot leave customer debt."""
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-DEBT", name="Perm Debt Widget")
    customer = await make_customer(client, admin, code="CUS-PERM-DEBT", name="Perm Debtor")
    limited = await _limited_headers(db_session, client, ["pos.access"], "debt")

    payload = {
        "payment_method": "CUSTOMER_DEBT",
        "customer_id": customer["id"],
        "amount_received": "0",
        "items": [{"product_id": product["id"], "quantity": "1"}],
    }
    denied = await client.post("/api/v1/pos/sales", json=payload, headers=limited)
    assert denied.status_code == 403, denied.text

    allowed = await client.post("/api/v1/pos/sales", json=payload, headers=admin)
    assert allowed.status_code == 201, allowed.text
    assert Decimal(allowed.json()["data"]["debt_amount"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_partial_payment_debt_sale_requires_pos_debt_sale(client, db_session):
    """Even a sale with a deposit is a debt sale when it leaves a balance."""
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-DEBT2", name="Perm Debt Widget 2")
    customer = await make_customer(client, admin, code="CUS-PERM-DEBT2", name="Perm Debtor 2")
    limited = await _limited_headers(db_session, client, ["pos.access"], "debt2")

    denied = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "customer_id": customer["id"],
            "amount_received": "1.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=limited,
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_print_requires_pos_print(client, db_session):
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-PRINT", name="Perm Print Widget")
    sale = await _cash_sale(client, admin, product["id"], quantity="1")

    without_print = await _limited_headers(db_session, client, ["pos.access"], "print-off")
    denied = await client.get(f"/api/v1/pos/sales/{sale['id']}/receipt", headers=without_print)
    assert denied.status_code == 403, denied.text

    with_print = await _limited_headers(db_session, client, ["pos.access", "pos.print"], "print-on")
    allowed = await client.get(f"/api/v1/pos/sales/{sale['id']}/receipt", headers=with_print)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["invoice_no"] == sale["invoice_no"]


@pytest.mark.asyncio
async def test_sale_edit_requires_pos_sale_edit(client, db_session):
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-EDIT", name="Perm Edit Widget")
    sale = await _cash_sale(client, admin, product["id"], quantity="2")
    payload = {
        "items": [{"product_id": product["id"], "quantity": "2"}],
    }

    without = await _limited_headers(db_session, client, ["pos.access"], "edit-off")
    denied = await client.patch(f"/api/v1/pos/sales/{sale['id']}", json=payload, headers=without)
    assert denied.status_code == 403, denied.text

    with_edit = await _limited_headers(
        db_session, client, ["pos.access", "pos.sale_edit"], "edit-on"
    )
    allowed = await client.patch(f"/api/v1/pos/sales/{sale['id']}", json=payload, headers=with_edit)
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_return_requires_pos_return(client, db_session):
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-RET", name="Perm Return Widget")
    sale = await _cash_sale(client, admin, product["id"], quantity="2")
    sale_item_id = sale["items"][0]["id"]
    payload = {
        "reason": "permission check",
        "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": True}],
    }

    without = await _limited_headers(db_session, client, ["pos.access"], "ret-off")
    denied = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return", json=payload, headers=without
    )
    assert denied.status_code == 403, denied.text

    # pos.return alone cannot issue a monetary refund (cash sale -> excess cash).
    return_only = await _limited_headers(db_session, client, ["pos.access", "pos.return"], "ret-norefund")
    with_return = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return", json=payload, headers=return_only
    )
    assert with_return.status_code == 403, with_return.text

    with_refund = await _limited_headers(
        db_session, client, ["pos.access", "pos.return", "pos.refund"], "ret-on"
    )
    allowed = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return", json=payload, headers=with_refund
    )
    assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_debt_reduction_return_needs_no_refund_permission(client, db_session):
    """Reducing an open debt is not a monetary refund: pos.return suffices."""
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="PERM-DR", name="Perm Debt Return")
    customer = await make_customer(client, admin, code="CUS-PERM-DR", name="Perm Debt Returner")
    sale = (
        await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CUSTOMER_DEBT",
                "customer_id": customer["id"],
                "amount_received": "0",
                "items": [{"product_id": product["id"], "quantity": "2"}],
            },
            headers=admin,
        )
    ).json()["data"]

    return_only = await _limited_headers(db_session, client, ["pos.access", "pos.return"], "dr")
    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "debt reduction only",
            "refund_disposition": "DEBT_REDUCTION",
            "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "1", "restock": True}],
        },
        headers=return_only,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_disposition"] == "DEBT_REDUCTION"
    assert Decimal(data["refund_paid_amount"]) == Decimal("0.00")
