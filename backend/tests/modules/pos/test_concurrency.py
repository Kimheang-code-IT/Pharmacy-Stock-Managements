"""Concurrency: oversell prevention and debt-payment races (spec section 9.4)."""

import asyncio
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import (
    balance_of,
    make_customer,
    make_stocked_product,
)
from tests.utils import admin_headers


@pytest.mark.asyncio
async def test_concurrent_sales_cannot_oversell(client):
    """Two simultaneous sales racing for the last units: exactly one wins."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="CONC-1", name="Race Widget", qty="1")

    async def sell():
        return await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CASH",
                "amount_received": "100.00",
                "items": [{"product_id": product["id"], "quantity": "1"}],
            },
            headers=headers,
        )

    first, second = await asyncio.gather(sell(), sell())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409], (first.text, second.text)

    assert await balance_of(client, headers, product["id"]) == Decimal("0.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=SALE", headers=headers
    )
    assert movements.json()["meta"]["total"] == 1, "only the winning sale may record a movement"


@pytest.mark.asyncio
async def test_concurrent_debt_payments_never_overpay(client):
    """Two simultaneous payments racing for the remaining debt: no overpayment."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="CONC-2", name="Race Debt Widget", qty="10")
    customer = await make_customer(client, headers, code="CUS-CONC-2", name="Race Debtor")

    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]
    remaining = Decimal(debt["remaining_amount"])
    assert remaining == Decimal("10.00")

    async def pay():
        return await client.post(
            f"/api/v1/customers/{customer['id']}/debts/{debt['id']}/payments",
            json={"amount": "8.00", "payment_method": "CASH"},
            headers=headers,
        )

    first, second = await asyncio.gather(pay(), pay())
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 422], (first.text, second.text)

    after = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    row = after.json()["data"][0]
    assert Decimal(row["paid_amount"]) == Decimal("8.00")
    assert Decimal(row["remaining_amount"]) == Decimal("2.00")
    assert Decimal(row["paid_amount"]) <= Decimal(row["original_amount"])
