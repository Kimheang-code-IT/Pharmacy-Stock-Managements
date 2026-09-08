"""Sale returns: restock movements, partial/full status, debt reduction (spec 2.1.7)."""

from decimal import Decimal

import pytest

from tests.modules.pos.helpers import (
    balance_of,
    make_customer,
    make_stocked_product,
)
from tests.utils import admin_headers


async def _new_sale(client, headers, product_id, *, quantity="4", payment_method="CASH", customer_id=None):
    payload = {
        "payment_method": payment_method,
        "amount_received": "1000.00",
        "items": [{"product_id": product_id, "quantity": quantity}],
    }
    if customer_id is not None:
        payload["customer_id"] = customer_id
    response = await client.post("/api/v1/pos/sales", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_partial_return_restocks_and_records_movement(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RET-1", name="Return Widget")
    sale = await _new_sale(client, headers, product["id"], quantity="4")
    sale_item_id = sale["items"][0]["id"]

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Customer changed mind",
            "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sale_return = response.json()["data"]
    assert sale_return["return_no"].startswith("SRT-")
    assert Decimal(sale_return["refund_amount"]) == Decimal("10.00")
    assert sale_return["items"][0]["restock"] is True

    detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    updated = detail.json()["data"]
    assert updated["sale_status"] == "PARTIAL_RETURN"
    assert Decimal(updated["items"][0]["returned_quantity"]) == Decimal("1")

    # Restocked exactly one unit.
    assert await balance_of(client, headers, product["id"]) == Decimal("7.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=SALE_RETURN", headers=headers
    )
    assert movements.json()["meta"]["total"] == 1
    assert Decimal(movements.json()["data"][0]["quantity_delta"]) == Decimal("1.0000")


@pytest.mark.asyncio
async def test_return_without_restock_does_not_change_stock(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RET-2", name="No Restock Widget")
    sale = await _new_sale(client, headers, product["id"], quantity="2")
    sale_item_id = sale["items"][0]["id"]

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Damaged by customer",
            "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": False}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert await balance_of(client, headers, product["id"]) == Decimal("8.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=SALE_RETURN", headers=headers
    )
    assert movements.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_return_rejects_more_than_remaining(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RET-3", name="Over Return Widget")
    sale = await _new_sale(client, headers, product["id"], quantity="2")
    sale_item_id = sale["items"][0]["id"]

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Too many",
            "items": [{"sale_item_id": sale_item_id, "quantity": "3", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_full_return_marks_sale_returned(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RET-4", name="Full Return Widget")
    sale = await _new_sale(client, headers, product["id"], quantity="2")
    sale_item_id = sale["items"][0]["id"]

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Full return",
            "items": [{"sale_item_id": sale_item_id, "quantity": "2", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text

    detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    assert detail.json()["data"]["sale_status"] == "RETURNED"

    # A fully returned sale cannot be returned again.
    again = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Again",
            "items": [{"sale_item_id": sale_item_id, "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_return_reduces_customer_debt(client):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RET-5", name="Debt Return Widget")
    customer = await make_customer(client, headers, code="CUS-RET-1", name="Return Debtor")

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale = sale.json()["data"]
    assert Decimal(sale["debt_amount"]) == Decimal("20.00")

    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "Returned one unit",
            "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]
    assert Decimal(debt["remaining_amount"]) == Decimal("10.00")
    assert Decimal(debt["paid_amount"]) == Decimal("10.00")
    assert debt["status"] == "PARTIAL"
