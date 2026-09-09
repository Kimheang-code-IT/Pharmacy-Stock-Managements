"""Live-mode FE/BE contract checks (Phase 9 alignment).

- SaleReturnRequest accepts `items` (canonical) AND `lines` (UI alias) with
  camelCase element keys.
- Stock In with payment_method records an immutable payment row when
  paid_amount > 0 (full payment or partial-with-debt).
- Line UOM symbol snapshots persist on stock_transaction_items and
  stock_movements.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.utils import DEFAULT_UOM_ID, admin_headers


async def _make_uom(client, headers, code: str) -> dict:
    response = await client.post(
        "/api/v1/uoms", json={"code": code, "name": f"Unit {code}", "symbol": code.lower()}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _make_pack_product(client, headers, *, sku: str) -> dict:
    pack = await _make_uom(client, headers, f"PK{sku[-3:]}")
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"C-{sku}", "name": f"Cat {sku}"}, headers=headers
        )
    ).json()["data"]
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": f"Product {sku}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "12.00",
            "uom_conversions": [
                {
                    "uom_id": str(DEFAULT_UOM_ID),
                    "factor_to_base": "1",
                    "sale_price": "12.00",
                    "is_default_sale": True,
                },
                {
                    "uom_id": pack["id"],
                    "uom_symbol": pack["symbol"],
                    "factor_to_base": "10",
                    "sale_price": "110.00",
                    "is_default_sale": False,
                },
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_sale_return_accepts_lines_alias_with_camel_keys(client):
    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="CTA-1")

    # Stock 20 base units, sell 2 packs via POS.
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "100.00",
            "items": [{"product_id": product["id"], "quantity": "20", "unit_cost": "5.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "1000.00",
            "items": [{
                "product_id": product["id"],
                "uom_id": next(
                    row["uom_id"] for row in product["uomConversions"]
                    if row["uom_id"] != str(DEFAULT_UOM_ID)
                ),
                "quantity": "2",
                "unit_price": "110.00",
            }],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    sale_item_id = sale_data["items"][0]["id"]

    # `lines` + camelCase saleItemId — the UI adapter dialect.
    response = await client.post(
        f"/api/v1/pos/sales/{sale_data['id']}/return",
        json={
            "reason": "UI alias body",
            "lines": [{"saleItemId": sale_item_id, "quantity": "1", "restock": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["return_no"].startswith("SRT-")


@pytest.mark.asyncio
async def test_stock_in_payment_method_records_payment_row(client, db_session):
    from app.modules.pos.models import Payment

    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="CTA-2")
    pack = next(
        row for row in product["uomConversions"] if row["uom_id"] != str(DEFAULT_UOM_ID)
    )

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "200.00",
            "payment_method": "BANK_QR",
            "items": [{
                "product_id": product["id"],
                "uom_id": pack["uom_id"],
                "uom_symbol": pack.get("uom_symbol"),
                "factor_to_base": pack["factor_to_base"],
                "quantity": "2",
                "unit_cost": "100.00",
            }],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    stock_in = response.json()["data"]

    # Payment row recorded for the paid amount (scoped to this document).
    payments = (
        await db_session.execute(
            select(Payment).where(
                Payment.payment_type.in_(("STOCK_IN_PAYMENT", "SUPPLIER_DEBT_PAYMENT")),
                Payment.reference_no == stock_in["document_no"],
            )
        )
    ).scalars().all()
    assert len(payments) == 1
    assert Decimal(payments[0].amount) == Decimal("200.00")
    assert payments[0].payment_method == "BANK_QR"
    assert payments[0].supplier_debt_id is None

    # Line UOM symbol snapshot persisted on item + movement.
    item = stock_in["items"][0]
    assert item["uom_symbol"] == (pack.get("uom_symbol") or "pktcta")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product['id']}&movement_type=STOCK_IN", headers=headers
    )
    assert movements.json()["data"][0]["uom_symbol"] == item["uom_symbol"]


@pytest.mark.asyncio
async def test_stock_in_partial_payment_records_debt_payment(client, db_session):
    from app.modules.pos.models import Payment

    headers = await admin_headers(client)
    product = await _make_pack_product(client, headers, sku="CTA-3")
    supplier = (
        await client.post("/api/v1/suppliers", json={"name": "CTA Supplier"}, headers=headers)
    ).json()["data"]

    response = await client.post(
        "/api/v1/stock/in",
        json={
            "supplier_id": supplier["id"],
            "paid_amount": "50.00",
            "payment_method": "CASH",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "10.00"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    stock_in = response.json()["data"]
    assert stock_in["debt_created"] is True

    payments = (
        await db_session.execute(
            select(Payment).where(
                Payment.payment_type == "SUPPLIER_DEBT_PAYMENT",
                Payment.supplier_debt_id.isnot(None),
                Payment.reference_no == stock_in["document_no"],
            )
        )
    ).scalars().all()
    assert len(payments) == 1
    assert Decimal(payments[0].amount) == Decimal("50.00")
    assert payments[0].supplier_debt_id is not None
