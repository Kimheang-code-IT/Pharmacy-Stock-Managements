"""Delivery Notes — deliverable qty, status workflow, no stock mutation (spec 2.1.9)."""

import asyncio
import uuid
from decimal import Decimal

import pytest

from tests.modules.pos.helpers import balance_of, make_customer, make_stocked_product
from tests.utils import admin_headers, create_user_with_role, login


async def _sale_two_lines(client, headers, tag: str):
    """Product A stocked 10, product B stocked 6; sale of 5 A + 2 B, cash."""
    product_a = await make_stocked_product(client, headers, sku=f"DNA-{tag}", name=f"Delivery A {tag}", qty="10")
    product_b = await make_stocked_product(client, headers, sku=f"DNB-{tag}", name=f"Delivery B {tag}", qty="6")
    customer = await make_customer(client, headers, code=f"DN-C-{tag}", name=f"Delivery Cust {tag}")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "500.00",
            "customer_id": customer["id"],
            "items": [
                {"product_id": product_a["id"], "quantity": "5"},
                {"product_id": product_b["id"], "quantity": "2"},
            ],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    line_a = next(i for i in sale_data["items"] if i["product_id"] == product_a["id"])
    line_b = next(i for i in sale_data["items"] if i["product_id"] == product_b["id"])
    return product_a, product_b, customer, sale_data, line_a, line_b


def _create_body(sale_id: str, line_id: str, qty, **extra) -> dict:
    return {
        "lines": [{"saleId": sale_id, "saleItemId": line_id, "qtyToDeliver": str(qty)}],
        **extra,
    }


@pytest.mark.asyncio
async def test_deliverable_items_and_partial_delivery(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product_a, product_b, customer, sale, line_a, line_b = await _sale_two_lines(client, headers, tag)

    deliverable = await client.get(f"/api/v1/sales/{sale['id']}/deliverable-items", headers=headers)
    assert deliverable.status_code == 200, deliverable.text
    payload = deliverable.json()["data"]
    assert payload["invoice_no"] == sale["invoice_no"]
    remaining = {item["sale_item_id"]: Decimal(item["qty_remaining"]) for item in payload["items"]}
    assert remaining[line_a["id"]] == Decimal("5.0000")
    assert remaining[line_b["id"]] == Decimal("2.0000")

    # First delivery note: partial (2 of 5 of line A), stays DRAFT.
    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": "2"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()["data"]
    assert note["status"] == "DRAFT"
    assert note["delivery_no"].startswith("DN-")
    assert note["invoice_nos"] == [sale["invoice_no"]]
    assert note["sales"][0]["sale_id"] == sale["id"]
    assert note["customer_id"] == customer["id"]
    assert note["delivery_phone"] == "0123456789"
    assert note["delivery_location"] == "Phnom Penh"
    assert Decimal(note["items"][0]["qty_ordered"]) == Decimal("5.0000")
    assert note["items"][0]["sale_id"] == sale["id"]

    # Remaining for line A drops to 3.
    deliverable = (await client.get(f"/api/v1/sales/{sale['id']}/deliverable-items", headers=headers)).json()["data"]
    remaining = {item["sale_item_id"]: Decimal(item["qty_remaining"]) for item in deliverable["items"]}
    assert remaining[line_a["id"]] == Decimal("3.0000")

    # Over-delivery across notes is rejected.
    over = await client.post(
        "/api/v1/delivery-notes",
        json={
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": "4"}],
        },
        headers=headers,
    )
    assert over.status_code == 422
    assert "remaining" in over.json()["detail"]["message"].lower()

    # Over-delivery within one note's lines is rejected too.
    within = await client.post(
        "/api/v1/delivery-notes",
        json={
            "lines": [
                {"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": "2"},
                {"saleId": sale["id"], "saleItemId": line_a["id"], "qtyToDeliver": "2"},
            ],
        },
        headers=headers,
    )
    assert within.status_code == 422

    # Delivery notes never touch stock.
    assert await balance_of(client, headers, product_a["id"]) == Decimal("5.0000")
    movements = await client.get(
        f"/api/v1/stock/movements?product_id={product_a['id']}", headers=headers
    )
    types = {m["movement_type"] for m in movements.json()["data"]}
    assert types <= {"STOCK_IN", "SALE"}, "delivery notes must not create stock movements"


@pytest.mark.asyncio
async def test_multi_invoice_same_customer_on_one_note(client):
    """One delivery note covers MANY invoices of the SAME customer (spec §2.1.9)."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNM-{tag}", name=f"DN Multi {tag}", qty="20")
    customer = await make_customer(client, headers, code=f"DN-M-{tag}", name=f"DN Multi Cust {tag}")

    sale_ids = []
    line_ids = []
    for i in range(2):
        sale = await client.post(
            "/api/v1/pos/sales",
            json={
                "payment_method": "CASH",
                "amount_received": "100.00",
                "customer_id": customer["id"],
                "items": [{"product_id": product["id"], "quantity": "3"}],
            },
            headers=headers,
        )
        assert sale.status_code == 201, sale.text
        sale_data = sale.json()["data"]
        sale_ids.append(sale_data["id"])
        line_ids.append(sale_data["items"][0]["id"])

    created = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [
                {"saleId": sale_ids[0], "saleItemId": line_ids[0], "qtyToDeliver": "3"},
                {"saleId": sale_ids[1], "saleItemId": line_ids[1], "qtyToDeliver": "2"},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()["data"]
    assert len(note["sales"]) == 2
    assert len(set(link["sale_id"] for link in note["sales"])) == 2
    assert len(note["invoice_nos"]) == 2
    assert note["invoice_no"].count(",") == 1  # comma-joined invoice display
    assert note["items_count"] == 2
    assert {item["sale_id"] for item in note["items"]} == set(sale_ids)

    # The deliverable-invoices picker no longer offers either invoice (or only
    # the partial remainder of the second one).
    picked = (
        await client.get("/api/v1/delivery-notes/deliverable-invoices", headers=headers)
    ).json()["data"]
    picked_ids = {row["sale_id"] for row in picked}
    assert sale_ids[0] not in picked_ids  # fully allocated

    # Search by invoice no finds the second (still partly deliverable) sale.
    invoice_no = next(link["invoice_no"] for link in note["sales"] if link["sale_id"] == sale_ids[1])
    searched = (
        await client.get(
            f"/api/v1/delivery-notes/deliverable-invoices?search={invoice_no}", headers=headers
        )
    ).json()["data"]
    assert {row["sale_id"] for row in searched} <= {sale_ids[1]}


@pytest.mark.asyncio
async def test_cross_customer_invoices_rejected(client):
    """All invoices on one delivery note must belong to the same customer."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNX-{tag}", name=f"DN Cross {tag}", qty="10")
    customer_a = await make_customer(client, headers, code=f"DN-XA-{tag}", name=f"DN Cross A {tag}")
    customer_b = await make_customer(client, headers, code=f"DN-XB-{tag}", name=f"DN Cross B {tag}")

    line_ids = {}
    sale_ids = {}
    for customer in (customer_a, customer_b):
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
        sale_ids[customer["id"]] = sale_data["id"]
        line_ids[customer["id"]] = sale_data["items"][0]["id"]

    mixed = await client.post(
        "/api/v1/delivery-notes",
        json={
            "deliveryPhone": "0123456789",
            "deliveryLocation": "Phnom Penh",
            "lines": [
                {"saleId": sale_ids[customer_a["id"]], "saleItemId": line_ids[customer_a["id"]], "qtyToDeliver": "1"},
                {"saleId": sale_ids[customer_b["id"]], "saleItemId": line_ids[customer_b["id"]], "qtyToDeliver": "1"},
            ],
        },
        headers=headers,
    )
    assert mixed.status_code == 422
    assert "same customer" in mixed.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_draft_edit_rules_and_status_workflow(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product_a, _product_b, _customer, sale, line_a, line_b = await _sale_two_lines(client, headers, tag)

    note = (
        await client.post(
            "/api/v1/delivery-notes",
            json=_create_body(sale["id"], line_a["id"], 2),
            headers=headers,
        )
    ).json()["data"]

    # Draft edits work: adjust qty and contact info.
    patched = await client.patch(
        f"/api/v1/delivery-notes/{note['id']}",
        json={
            "delivery_phone": "012999999",
            "delivery_location": "Siem Reap",
            "lines": [{"saleId": sale["id"], "saleItemId": line_a["id"], "qty_to_deliver": "3"}],
        },
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert Decimal(patched.json()["data"]["items"][0]["qty_to_deliver"]) == Decimal("3.0000")
    assert patched.json()["data"]["delivery_phone"] == "012999999"
    assert patched.json()["data"]["delivery_location"] == "Siem Reap"

    # Illegal transition: deliver a draft (Draft → Delivered is not allowed).
    early = await client.post(f"/api/v1/delivery-notes/{note['id']}/deliver", headers=headers)
    assert early.status_code == 409

    confirmed = await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"

    # Draft-only editing: confirmed notes are locked.
    locked = await client.patch(
        f"/api/v1/delivery-notes/{note['id']}", json={"delivery_phone": "011"}, headers=headers
    )
    assert locked.status_code == 409

    out = await client.post(f"/api/v1/delivery-notes/{note['id']}/out-for-delivery", headers=headers)
    assert out.status_code == 200
    assert out.json()["data"]["status"] == "OUT_FOR_DELIVERY"

    delivered = await client.post(f"/api/v1/delivery-notes/{note['id']}/deliver", headers=headers)
    assert delivered.status_code == 200, delivered.text
    body = delivered.json()["data"]
    assert body["status"] == "DELIVERED"
    assert body["delivered_at"] is not None
    assert all(Decimal(item["qty_delivered"]) == Decimal(item["qty_to_deliver"]) for item in body["items"])

    # Delivered is terminal.
    again = await client.post(f"/api/v1/delivery-notes/{note['id']}/cancel", json={"reason": "nope"}, headers=headers)
    assert again.status_code == 409

    # Remaining for line A reflects the delivered 3.
    deliverable = (await client.get(f"/api/v1/sales/{sale['id']}/deliverable-items", headers=headers)).json()["data"]
    remaining = {item["sale_item_id"]: Decimal(item["qty_remaining"]) for item in deliverable["items"]}
    assert remaining[line_a["id"]] == Decimal("2.0000")
    assert await balance_of(client, headers, product_a["id"]) == Decimal("5.0000")


@pytest.mark.asyncio
async def test_phone_and_location_required_before_confirm(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNP-{tag}", name=f"DN Phone {tag}", qty="5")
    customer_no_contact = (
        await client.post(
            "/api/v1/customers",
            json={"code": f"DN-NP-{tag}", "name": f"DN No Phone {tag}", "status": "ACTIVE"},
            headers=headers,
        )
    ).json()["data"]
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "50.00",
            "customer_id": customer_no_contact["id"],
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    line_id = sale.json()["data"]["items"][0]["id"]

    note = (
        await client.post(
            "/api/v1/delivery-notes",
            json=_create_body(sale.json()["data"]["id"], line_id, 1),
            headers=headers,
        )
    ).json()["data"]
    assert note["status"] == "DRAFT"

    # Confirm without phone/location is rejected.
    missing = await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=headers)
    assert missing.status_code == 422

    patched = await client.patch(
        f"/api/v1/delivery-notes/{note['id']}",
        json={"delivery_phone": "012999888", "delivery_location": "Battambang"},
        headers=headers,
    )
    assert patched.status_code == 200
    confirmed = await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text


@pytest.mark.asyncio
async def test_cancel_releases_remaining_qty(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, _customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)

    note = (
        await client.post(
            "/api/v1/delivery-notes",
            json=_create_body(sale["id"], line_a["id"], 5),
            headers=headers,
        )
    ).json()["data"]

    deliverable = (await client.get(f"/api/v1/sales/{sale['id']}/deliverable-items", headers=headers)).json()["data"]
    remaining = {item["sale_item_id"]: Decimal(item["qty_remaining"]) for item in deliverable["items"]}
    assert remaining[line_a["id"]] == Decimal("0.0000")

    cancelled = await client.post(
        f"/api/v1/delivery-notes/{note['id']}/cancel", json={"reason": "customer away"}, headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert cancelled.json()["data"]["cancel_reason"] == "customer away"

    deliverable = (await client.get(f"/api/v1/sales/{sale['id']}/deliverable-items", headers=headers)).json()["data"]
    remaining = {item["sale_item_id"]: Decimal(item["qty_remaining"]) for item in deliverable["items"]}
    assert remaining[line_a["id"]] == Decimal("5.0000"), "cancel must release the reserved quantity"

    # Cancelled notes cannot transition anymore.
    confirm = await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=headers)
    assert confirm.status_code == 409


@pytest.mark.asyncio
async def test_returned_qty_is_not_deliverable(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DR-{tag}", name=f"DelRet {tag}", qty="8")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "4"}],
        },
        headers=headers,
    )
    sale_data = sale.json()["data"]
    line_id = sale_data["items"][0]["id"]

    returned = await client.post(
        f"/api/v1/pos/sales/{sale_data['id']}/return",
        json={"reason": "damaged in cart", "items": [{"sale_item_id": line_id, "quantity": "2", "restock": True}]},
        headers=headers,
    )
    assert returned.status_code == 201, returned.text

    deliverable = (await client.get(f"/api/v1/sales/{sale_data['id']}/deliverable-items", headers=headers)).json()["data"]
    row = deliverable["items"][0]
    assert Decimal(row["qty_ordered"]) == Decimal("2.0000")  # 4 sold - 2 returned
    assert Decimal(row["qty_remaining"]) == Decimal("2.0000")

    # Delivering more than the return-adjusted remaining is rejected.
    over = await client.post(
        "/api/v1/delivery-notes",
        json={"lines": [{"saleId": sale_data["id"], "saleItemId": line_id, "qtyToDeliver": "3"}]},
        headers=headers,
    )
    assert over.status_code == 422


@pytest.mark.asyncio
async def test_print_payload_and_customer_listing(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    _product_a, _product_b, customer, sale, line_a, _line_b = await _sale_two_lines(client, headers, tag)

    note = (
        await client.post(
            "/api/v1/delivery-notes",
            json=_create_body(sale["id"], line_a["id"], 1),
            headers=headers,
        )
    ).json()["data"]

    printed = await client.get(f"/api/v1/delivery-notes/{note['id']}/print", headers=headers)
    assert printed.status_code == 200, printed.text
    payload = printed.json()["data"]
    assert payload["delivery_no"] == note["delivery_no"]
    assert payload["document_title"] == "Delivery Note"
    assert payload["invoice_nos"] == [sale["invoice_no"]]
    assert payload["signature_blocks"] == ["Receiver", "Delivery staff"]
    assert len(payload["lines"]) == 1

    customer_notes = await client.get(f"/api/v1/customers/{customer['id']}/delivery-notes", headers=headers)
    assert customer_notes.status_code == 200
    assert note["id"] in {n["id"] for n in customer_notes.json()["data"]}

    # Sale item responses expose the UOM snapshot captured at sale time.
    sale_detail = await client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers)
    assert sale_detail.status_code == 200
    sale_item = sale_detail.json()["data"]["items"][0]
    assert sale_item["uom_symbol"] == "ea"

    # POS post-sale entry point creates a note for the same sale.
    pos_note = await client.post(
        f"/api/v1/pos/sales/{sale['id']}/delivery-notes",
        json=_create_body(sale["id"], line_a["id"], 1),
        headers=headers,
    )
    assert pos_note.status_code == 201, pos_note.text
    assert pos_note.json()["data"]["delivery_no"].startswith("DN-")


@pytest.mark.asyncio
async def test_delivery_permissions_enforced(client, db_session):
    await create_user_with_role(
        db_session,
        email="dn-viewer@example.com",
        password="dnviewer1",
        role_name="DN Viewer",
        permissions=["delivery.view"],
    )
    await db_session.commit()
    data = await login(client, "dn-viewer@example.com", "dnviewer1")
    viewer = {"Authorization": f"Bearer {data['access_token']}"}

    anon = await client.get("/api/v1/delivery-notes")
    assert anon.status_code == 401

    # Viewer can read but not create/confirm.
    assert (await client.get("/api/v1/delivery-notes", headers=viewer)).status_code == 200
    assert (
        await client.post(
            "/api/v1/delivery-notes",
            json={"lines": [{"saleId": str(uuid.uuid4()), "saleItemId": str(uuid.uuid4()), "qtyToDeliver": "1"}]},
            headers=viewer,
        )
    ).status_code == 403

    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNP-{tag}", name=f"DNPerm {tag}", qty="5")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    sale_id = sale.json()["data"]["id"]
    line_id = sale.json()["data"]["items"][0]["id"]

    note = (
        await client.post(
            "/api/v1/delivery-notes",
            json=_create_body(sale_id, line_id, 1),
            headers=headers,
        )
    ).json()["data"]

    assert (await client.post(f"/api/v1/delivery-notes/{note['id']}/confirm", headers=viewer)).status_code == 403
    assert (await client.post(f"/api/v1/delivery-notes/{note['id']}/deliver", headers=viewer)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/delivery-notes/{note['id']}/cancel", json={"reason": "x"}, headers=viewer
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_concurrent_delivery_note_creation_allocates_distinct_numbers(client):
    """Parallel creates against one sequence: no duplicate DN numbers, no over-delivery."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNC-{tag}", name=f"DN Concurrency {tag}", qty="4")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "4"}],
        },
        headers=headers,
    )
    sale_id = sale.json()["data"]["id"]
    line_id = sale.json()["data"]["items"][0]["id"]

    async def create(qty: str):
        return await client.post(
            "/api/v1/delivery-notes",
            json={
                "deliveryPhone": "0123456789",
                "deliveryLocation": "Phnom Penh",
                "lines": [{"saleId": sale_id, "saleItemId": line_id, "qtyToDeliver": qty}],
            },
            headers=headers,
        )

    # Two racing creates each asking 3 of 4 remaining: the sale-row lock
    # serializes deliverable-qty validation, so exactly one wins.
    first, second = await asyncio.gather(create("3"), create("3"))
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 422], (first.text, second.text)

    listing = await client.get(
        "/api/v1/delivery-notes", params={"q": sale.json()["data"]["invoice_no"]}, headers=headers
    )
    numbers = [n["delivery_no"] for n in listing.json()["data"]]
    assert len(numbers) == len(set(numbers)) == 1

    # The winner allocated 3 of 4: one more unit fits, then over-delivery is rejected.
    assert (await create("1")).status_code == 201
    assert (await create("1")).status_code == 422


@pytest.mark.asyncio
async def test_delivery_note_requires_completed_sale(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DNS-{tag}", name=f"DN Sale Status {tag}", qty="3")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    sale_id = sale.json()["data"]["id"]
    line_id = sale.json()["data"]["items"][0]["id"]

    await client.post(
        f"/api/v1/pos/sales/{sale_id}/return",
        json={"reason": "full return", "items": [{"sale_item_id": line_id, "quantity": "1", "restock": True}]},
        headers=headers,
    )
    fully_returned = await client.post(
        "/api/v1/delivery-notes",
        json={"lines": [{"saleId": sale_id, "saleItemId": line_id, "qtyToDeliver": "1"}]},
        headers=headers,
    )
    # A fully returned sale (RETURNED status) cannot produce delivery notes.
    assert fully_returned.status_code == 409
