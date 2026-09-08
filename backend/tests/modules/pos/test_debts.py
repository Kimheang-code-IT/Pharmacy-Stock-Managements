"""Customer debt payments: immutability, overpayment rejection, permissions (spec 2.1.8)."""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers, create_user_with_role, login


@pytest.fixture
async def viewer_only_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email="debt-viewer@example.com",
        password="viewerpass1",
        role_name="Debt Viewer",
        permissions=["customer.view"],
    )
    await db_session.commit()
    data = await login(client, "debt-viewer@example.com", "viewerpass1")
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _debt_sale(client, headers, *, total="20.00", deposit="0.00", sku="DBT-1"):
    product = await make_stocked_product(client, headers, sku=sku, name="Debt Payment Widget", qty="10")
    customer = await make_customer(client, headers, code=f"CUS-{sku}", name="Debt Payer")
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "amount_received": deposit,
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]
    return customer, debt


@pytest.mark.asyncio
async def test_partial_then_full_payment_sets_status_paid(client):
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-1")

    first = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH", "reference_no": "RC1"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    payment = first.json()["data"]
    assert payment["payment_no"].startswith("CDP-")
    assert payment["payment_type"] == "CUSTOMER_DEBT_PAYMENT"
    assert payment["customer_debt_id"] == debt["id"]

    after_first = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    row = after_first.json()["data"][0]
    assert row["status"] == "PARTIAL"
    assert Decimal(row["remaining_amount"]) == Decimal("15.00")

    second = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "15.00", "payment_method": "BANK_QR", "reference_no": "RC2"},
        headers=headers,
    )
    assert second.status_code == 201, second.text

    after_second = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    row = after_second.json()["data"][0]
    assert row["status"] == "PAID"
    assert Decimal(row["remaining_amount"]) == Decimal("0.00")
    assert Decimal(row["paid_amount"]) == Decimal("20.00")


@pytest.mark.asyncio
async def test_payment_rejects_overpayment(client):
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-2")

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "25.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "amount" in detail.get("field_errors", {})


@pytest.mark.asyncio
async def test_payment_rejects_settled_debt(client):
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-3")

    pay = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "20.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert pay.status_code == 201

    again = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "1.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_payment_history_is_immutable_and_complete(client):
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-4", deposit="2.00")

    await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "8.00", "payment_method": "CASH"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "10.00", "payment_method": "BANK_QR"},
        headers=headers,
    )

    history = await client.get(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments", headers=headers
    )
    assert history.status_code == 200, history.text
    rows = history.json()["data"]
    # Deposit at sale time + two payments, in chronological order.
    assert len(rows) == 3
    assert rows[0]["payment_type"] == "SALE_PAYMENT"
    assert Decimal(rows[0]["amount"]) == Decimal("2.00")
    assert all(r["payment_type"] == "CUSTOMER_DEBT_PAYMENT" for r in rows[1:])
    assert Decimal(sum(Decimal(r["amount"]) for r in rows)) == Decimal("20.00")

    # There is no edit/delete endpoint for payments: immutability by design.
    mutation_methods = {"PUT", "PATCH", "DELETE"}
    for route in client._transport.app.routes:
        path = getattr(route, "path", "")
        if "payment" in path and mutation_methods & set(getattr(route, "methods", set())):
            pytest.fail(f"payments must be immutable, found mutation route: {path}")


@pytest.mark.asyncio
async def test_payment_requires_permission(client, viewer_only_headers):
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-5")

    denied = await client.post(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=viewer_only_headers,
    )
    assert denied.status_code == 403

    # Viewing history is allowed with customer.view.
    history = await client.get(
        f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments", headers=viewer_only_headers
    )
    assert history.status_code == 200


@pytest.mark.asyncio
async def test_payment_scoped_to_owning_customer(client):
    """IDOR: a debt under customer A is not payable/reachable via customer B."""
    headers = await admin_headers(client)
    customer, debt = await _debt_sale(client, headers, sku="DBT-6")
    other = await make_customer(client, headers, code="CUS-DBT-OTHER", name="Other Customer")

    response = await client.post(
        f"/api/v1/customers/{other['id']}/debts/{debt['id']}/payments",
        json={"amount": "5.00", "payment_method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 404

    history = await client.get(
        f"/api/v1/customers/{other['id']}/debts/{debt['id']}/payments", headers=headers
    )
    assert history.status_code == 404
