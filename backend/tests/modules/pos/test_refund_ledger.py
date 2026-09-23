"""Sale-return refund ledger (spec: proper refund-payment ledger).

A return records how the refund was settled. Only CASH_REFUND/BANK_QR_REFUND
move money and create a SALE_REFUND cash-out row; DEBT_REDUCTION and store
credit create no cash movement. Multiple partial returns stay safe and a refund
can never exceed what is still refundable on the sale.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.pos.models import Payment
from tests.modules.pos.helpers import (
    balance_of,
    make_customer,
    make_stocked_product,
)
from tests.utils import admin_headers


async def _sale(client, headers, product_id, *, quantity, method="CASH", amount="1000.00", customer_id=None, discount=None):
    payload = {
        "payment_method": method,
        "amount_received": amount,
        "items": [{"product_id": product_id, "quantity": quantity}],
    }
    if customer_id is not None:
        payload["customer_id"] = customer_id
    if discount is not None:
        payload["discount"] = discount
    response = await client.post("/api/v1/pos/sales", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _return(client, headers, sale, item_index=0, quantity="1", **extra):
    body = {
        "reason": "refund ledger test",
        "items": [
            {"sale_item_id": sale["items"][item_index]["id"], "quantity": quantity, "restock": True}
        ],
    }
    body.update(extra)
    return await client.post(f"/api/v1/pos/sales/{sale['id']}/return", json=body, headers=headers)


async def _refund_payments(db_session, sale_return_id):
    result = await db_session.execute(
        select(Payment).where(Payment.sale_return_id == sale_return_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_cash_refund_records_ledger_payment(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-CASH", name="Cash Refund Widget")
    sale = await _sale(client, headers, product["id"], quantity="2")

    response = await _return(client, headers, sale, quantity="1", refund_disposition="CASH_REFUND")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_disposition"] == "CASH_REFUND"
    assert data["refund_method"] == "CASH"
    assert Decimal(data["refund_paid_amount"]) == Decimal("10.00")
    assert Decimal(data["refund_amount"]) == Decimal("10.00")

    payments = await _refund_payments(db_session, data["id"])
    assert len(payments) == 1
    payment = payments[0]
    assert payment.payment_type == "SALE_REFUND"
    assert payment.payment_method == "CASH"
    assert payment.amount == Decimal("10.00")
    assert str(payment.sale_id) == sale["id"]

    # Restocked one unit.
    assert await balance_of(client, headers, product["id"]) == Decimal("9.0000")


@pytest.mark.asyncio
async def test_bank_refund_uses_bank_method(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-BANK", name="Bank Refund Widget")
    sale = await _sale(client, headers, product["id"], quantity="1")

    response = await _return(
        client, headers, sale, quantity="1", refund_disposition="BANK_QR_REFUND"
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_method"] == "BANK_QR"

    payments = await _refund_payments(db_session, data["id"])
    assert len(payments) == 1
    assert payments[0].payment_type == "SALE_REFUND"
    assert payments[0].payment_method == "BANK_QR"


@pytest.mark.asyncio
async def test_debt_reduction_creates_no_cash_movement(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-DEBT", name="Debt Refund Widget")
    customer = await make_customer(client, headers, code="CUS-RF-DEBT", name="Refund Debtor")
    sale = await _sale(
        client, headers, product["id"], quantity="2", method="CUSTOMER_DEBT", amount="0", customer_id=customer["id"]
    )
    assert Decimal(sale["debt_amount"]) == Decimal("20.00")

    response = await _return(client, headers, sale, quantity="1")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_disposition"] == "DEBT_REDUCTION"
    assert Decimal(data["refund_paid_amount"]) == Decimal("0.00")
    assert Decimal(data["debt_reduction"]) == Decimal("10.00")
    assert await _refund_payments(db_session, data["id"]) == []

    debts = await client.get(f"/api/v1/customers/{customer['id']}/debts", headers=headers)
    debt = debts.json()["data"][0]
    assert Decimal(debt["remaining_amount"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_refund_exceeding_debt_splits_debt_and_cash(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-SPLIT", name="Split Refund Widget")
    customer = await make_customer(client, headers, code="CUS-RF-SPLIT", name="Split Debtor")
    # Total 20.00, paid 15.00 -> 5.00 open debt.
    sale = await _sale(
        client, headers, product["id"], quantity="2", method="CUSTOMER_DEBT", amount="15", customer_id=customer["id"]
    )
    assert Decimal(sale["debt_amount"]) == Decimal("5.00")

    # DEBT_REDUCTION cannot absorb the 20.00 refund (only 5.00 debt).
    denied = await _return(
        client, headers, sale, quantity="2", refund_disposition="DEBT_REDUCTION"
    )
    assert denied.status_code == 422, denied.text

    # CASH_REFUND reduces the debt first, then pays the 15.00 excess.
    response = await _return(client, headers, sale, quantity="2", refund_disposition="CASH_REFUND")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert Decimal(data["debt_reduction"]) == Decimal("5.00")
    assert Decimal(data["refund_paid_amount"]) == Decimal("15.00")
    payments = await _refund_payments(db_session, data["id"])
    assert len(payments) == 1 and payments[0].amount == Decimal("15.00")


@pytest.mark.asyncio
async def test_store_credit_is_not_cash(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-CREDIT", name="Credit Refund Widget")
    sale = await _sale(client, headers, product["id"], quantity="1")

    response = await _return(
        client, headers, sale, quantity="1", refund_disposition="CUSTOMER_CREDIT"
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_disposition"] == "CUSTOMER_CREDIT"
    assert Decimal(data["credit_amount"]) == Decimal("10.00")
    assert Decimal(data["refund_paid_amount"]) == Decimal("0.00")
    assert await _refund_payments(db_session, data["id"]) == []


@pytest.mark.asyncio
async def test_no_refund_requires_reason(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-NO", name="No Refund Widget")
    sale = await _sale(client, headers, product["id"], quantity="1")

    missing_reason = await _return(client, headers, sale, quantity="1", refund_disposition="NO_REFUND")
    assert missing_reason.status_code == 422, missing_reason.text

    response = await _return(
        client,
        headers,
        sale,
        quantity="1",
        refund_disposition="NO_REFUND",
        refund_note="Customer waived the refund",
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["refund_disposition"] == "NO_REFUND"
    assert Decimal(data["refund_paid_amount"]) == Decimal("0.00")
    assert Decimal(data["debt_reduction"]) == Decimal("0.00")
    assert await _refund_payments(db_session, data["id"]) == []


@pytest.mark.asyncio
async def test_header_discount_allocated_to_refund(client):
    """A header discount is spread over lines, so a refund never exceeds what
    was actually paid for the returned units."""
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-HDR", name="Header Discount Widget")
    # 2 x 10.00 = 20.00 subtotal, header discount 4.00 -> grand 16.00.
    sale = await _sale(client, headers, product["id"], quantity="2", discount="4.00")
    assert Decimal(sale["grand_total"]) == Decimal("16.00")

    response = await _return(client, headers, sale, quantity="1", refund_disposition="CASH_REFUND")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    # Half of the net 16.00 = 8.00 (10.00 line less its 2.00 discount share).
    assert Decimal(data["refund_amount"]) == Decimal("8.00")
    assert Decimal(data["refund_paid_amount"]) == Decimal("8.00")


@pytest.mark.asyncio
async def test_multiple_partial_returns_are_safe(client, db_session):
    headers = await admin_headers(client)
    product = await make_stocked_product(client, headers, sku="RF-MULTI", name="Multi Return Widget")
    sale = await _sale(client, headers, product["id"], quantity="3")

    first = await _return(client, headers, sale, quantity="1", refund_disposition="CASH_REFUND")
    assert first.status_code == 201, first.text
    second = await _return(client, headers, sale, quantity="1", refund_disposition="CASH_REFUND")
    assert second.status_code == 201, second.text

    # Only 1 unit remains; a 2-unit return must be rejected.
    over = await _return(client, headers, sale, quantity="2", refund_disposition="CASH_REFUND")
    assert over.status_code == 422, over.text

    detail = (await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)).json()["data"]
    assert Decimal(detail["items"][0]["returned_quantity"]) == Decimal("2")
    # Two refunds of 10.00 each, never more than the 30.00 goods revenue.
    refunds = await client.get(
        f"/api/v1/reports/sale-returns?q={sale['invoice_no']}", headers=headers
    )
    rows = refunds.json()["data"]
    assert sum(Decimal(r["refund_amount"]) for r in rows) == Decimal("20.00")


@pytest.mark.asyncio
async def test_cash_refund_appears_in_cash_flow(client):
    headers = await admin_headers(client)
    baseline = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]

    product = await make_stocked_product(client, headers, sku="RF-FIN", name="Refund Finance Widget")
    sale = await _sale(client, headers, product["id"], quantity="2")
    response = await _return(client, headers, sale, quantity="1", refund_disposition="CASH_REFUND")
    assert response.status_code == 201, response.text

    after = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    refund_delta = Decimal(after["cash_flow"]["customer_refunds_paid"]) - Decimal(
        baseline["cash_flow"]["customer_refunds_paid"]
    )
    assert refund_delta == Decimal("10.00")
    # A cash refund is cash-out, never income and never a P&L expense line.
    assert Decimal(after["cash_flow"]["net_cash_flow"]) - Decimal(
        baseline["cash_flow"]["net_cash_flow"]
    ) == Decimal("-10.00")


@pytest.mark.asyncio
async def test_non_restock_return_reduces_revenue_not_cogs(client):
    """A non-restocked return lowers net sales but must NOT reverse inventory
    cost (the goods were not recovered)."""
    headers = await admin_headers(client)
    baseline = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]

    product = await make_stocked_product(
        client, headers, sku="RF-NR", name="No Restock Return", unit_cost="2.00", selling_price="10.00"
    )
    sale = await _sale(client, headers, product["id"], quantity="2")
    response = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/return",
        json={
            "reason": "damaged by customer",
            "refund_disposition": "CASH_REFUND",
            "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "1", "restock": False}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text

    after = (await client.get("/api/v1/reports/finance", headers=headers)).json()["data"]
    pl = after["profit_and_loss"]
    bl = baseline["profit_and_loss"]
    assert Decimal(pl["sale_returns"]) - Decimal(bl["sale_returns"]) == Decimal("10.00")
    # COGS rises only by the original sale (2 units x 2.00 = 4.00) and is NOT
    # reversed by the non-restocked return: the goods were not recovered.
    assert Decimal(pl["cost_of_goods_sold"]) - Decimal(bl["cost_of_goods_sold"]) == Decimal("4.00")
    # Net effect on gross profit: +16 (sale) - 10 (return) = +6.
    assert Decimal(pl["gross_profit"]) - Decimal(bl["gross_profit"]) == Decimal("6.00")
