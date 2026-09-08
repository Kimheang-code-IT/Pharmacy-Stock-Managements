"""Delivery Notes service — spec section 2.1.9.

Rules enforced here:
- Delivery notes are created from confirmed sales of the SAME customer; they
  NEVER mutate stock (stock was already reduced by the POS sale — no second
  stock-out).
- One note may cover MANY invoices (delivery_note_sales); every line links
  back to its parent sale (delivery_note_items.sale_id).
- qty_to_deliver per sale line can never exceed the remaining undelivered
  quantity across all non-cancelled delivery notes.
- Phone + location are required before Confirm / Out for Delivery / Delivered
  (editable header inputs — never a driver/vehicle/schedule form).
- Cancelled notes release their quantities back to the sale's remaining pool.
- Delivered is terminal for quantity purposes and sets delivered_at.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.customers.models import Customer
from app.modules.delivery_notes.models import DeliveryNote, DeliveryNoteItem, DeliveryNoteSale
from app.modules.delivery_notes.repository import DeliveryNoteRepository
from app.modules.delivery_notes.schemas import (
    DeliverableInvoiceOut,
    DeliverableItemOut,
    DeliverableItemsOut,
    DeliveryNoteCreate,
    DeliveryNoteItemOut,
    DeliveryNoteLineCreate,
    DeliveryNoteOut,
    DeliveryNoteSaleOut,
)
from app.modules.pos.models import Sale, SaleItem
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number

# Sales from which products can still be delivered.
DELIVERABLE_SALE_STATUSES = ("COMPLETED", "PARTIAL_RETURN")
FOUR = Decimal("0.0001")

# §2.1.9 Update Status transition table; Delivered/Cancelled are terminal.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DeliveryNote.STATUS_DRAFT: {
        DeliveryNote.STATUS_CONFIRMED,
        DeliveryNote.STATUS_CANCELLED,
    },
    DeliveryNote.STATUS_CONFIRMED: {
        DeliveryNote.STATUS_OUT_FOR_DELIVERY,
        DeliveryNote.STATUS_DELIVERED,
        DeliveryNote.STATUS_CANCELLED,
    },
    DeliveryNote.STATUS_OUT_FOR_DELIVERY: {
        DeliveryNote.STATUS_DELIVERED,
        DeliveryNote.STATUS_CANCELLED,
    },
    DeliveryNote.STATUS_DELIVERED: set(),
    DeliveryNote.STATUS_CANCELLED: set(),
}

STATUS_TRANSITION_AUDIT_ACTION = {
    DeliveryNote.STATUS_CONFIRMED: "delivery_confirmed",
    DeliveryNote.STATUS_OUT_FOR_DELIVERY: "delivery_out_for_delivery",
    DeliveryNote.STATUS_DELIVERED: "delivery_delivered",
    DeliveryNote.STATUS_CANCELLED: "delivery_cancelled",
}

# Legacy verb aliases of the same transition service (§5.13).
ACTION_TO_STATUS = {
    "confirm": DeliveryNote.STATUS_CONFIRMED,
    "out_for_delivery": DeliveryNote.STATUS_OUT_FOR_DELIVERY,
    "outForDelivery": DeliveryNote.STATUS_OUT_FOR_DELIVERY,
    "deliver": DeliveryNote.STATUS_DELIVERED,
    "cancel": DeliveryNote.STATUS_CANCELLED,
}


def _q4(value) -> Decimal:
    return Decimal(value).quantize(FOUR)


class _SaleGroup:
    """Requested lines of one parent sale, with the sale's line lookup."""

    def __init__(self, sale: Sale, sale_items: dict[uuid.UUID, SaleItem]) -> None:
        self.sale = sale
        self.sale_items = sale_items
        self.requested: list[tuple[SaleItem, Decimal]] = []


class DeliveryNoteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DeliveryNoteRepository(session)

    # ------------------------------------------------------------ read model

    async def _sale(self, sale_id: uuid.UUID) -> Sale:
        sale = await self.session.get(Sale, sale_id)
        if sale is None:
            raise NotFoundError("Sale not found")
        return sale

    async def _lock_sale(self, sale_id: uuid.UUID) -> None:
        """Serialize deliverable-qty validation per sale (over-delivery races)."""
        await self.session.execute(select(Sale.id).where(Sale.id == sale_id).with_for_update())

    async def _sale_items(self, sale_id: uuid.UUID) -> list[SaleItem]:
        result = await self.session.execute(
            select(SaleItem).where(SaleItem.sale_id == sale_id).order_by(SaleItem.created_at)
        )
        return list(result.scalars().all())

    async def deliverable_items(self, sale_id: uuid.UUID) -> DeliverableItemsOut:
        """What remains deliverable for a sale (drives the create form)."""
        sale = await self._sale(sale_id)
        allocated = await self.repo.allocated_by_sale_item(sale_id)

        items: list[DeliverableItemOut] = []
        for sale_item in await self._sale_items(sale_id):
            ordered = _q4(sale_item.quantity - sale_item.returned_quantity)
            line_allocated = _q4(allocated.get(sale_item.id, Decimal("0")))
            items.append(
                DeliverableItemOut(
                    sale_item_id=sale_item.id,
                    product_id=sale_item.product_id,
                    product_name=sale_item.product_name,
                    sku=sale_item.sku,
                    uom_symbol=sale_item.uom_symbol,
                    qty_ordered=ordered,
                    qty_returned=_q4(sale_item.returned_quantity),
                    qty_allocated=line_allocated,
                    qty_delivered=_q4(allocated.get(sale_item.id, Decimal("0"))),
                    qty_remaining=_q4(ordered - line_allocated),
                )
            )
        return DeliverableItemsOut(
            sale_id=sale.id,
            invoice_no=sale.invoice_no,
            sale_status=sale.sale_status,
            customer_id=sale.customer_id,
            items=items,
        )

    async def deliverable_invoices(
        self,
        *,
        q: str | None = None,
        customer_id: uuid.UUID | None = None,
        start=None,
        end=None,
        limit: int = 50,
    ) -> list[DeliverableInvoiceOut]:
        """Confirmed sales with remaining deliverable qty (create-page picker).

        Live search by invoice no (customer name / phone secondary).
        """
        conditions = [Sale.sale_status.in_(DELIVERABLE_SALE_STATUSES)]
        if customer_id is not None:
            conditions.append(Sale.customer_id == customer_id)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            customer_ids = (
                select(Customer.id).where(Customer.name.ilike(pattern) | Customer.phone.ilike(pattern))
            )
            conditions.append(Sale.invoice_no.ilike(pattern) | Sale.customer_id.in_(customer_ids))
        if start is not None:
            conditions.append(Sale.sale_date >= start)
        if end is not None:
            conditions.append(Sale.sale_date <= end)

        stmt = (
            select(Sale)
            .where(*conditions)
            .order_by(Sale.sale_date.desc())
            .limit(max(1, min(limit, 100)))
        )
        sales = list((await self.session.execute(stmt)).scalars().all())
        if not sales:
            return []

        customers: dict[uuid.UUID, Customer] = {}
        for customer_id_ in {sale.customer_id for sale in sales}:
            customer = await self.session.get(Customer, customer_id_)
            if customer is not None:
                customers[customer.id] = customer

        out: list[DeliverableInvoiceOut] = []
        for sale in sales:
            deliverable = await self.deliverable_items(sale.id)
            remaining = sum((item.qty_remaining for item in deliverable.items), Decimal("0"))
            if remaining <= 0:
                continue
            customer = customers.get(sale.customer_id)
            out.append(
                DeliverableInvoiceOut(
                    sale_id=sale.id,
                    saleId=sale.id,
                    invoice_no=sale.invoice_no,
                    invoiceNo=sale.invoice_no,
                    sale_date=sale.sale_date,
                    sale_status=sale.sale_status,
                    customer_id=sale.customer_id,
                    customer_name=customer.name if customer else None,
                    phone=(customer.phone if customer else None) or None,
                    location=(customer.address if customer else None) or None,
                    qty_remaining=_q4(remaining),
                    items=deliverable.items,
                )
            )
        return out

    async def _validate_lines(
        self,
        groups: dict[uuid.UUID, _SaleGroup],
        *,
        exclude_note_id: uuid.UUID | None = None,
    ) -> None:
        """qty_to_deliver must fit within remaining undelivered per sale line."""
        for sale_id, group in groups.items():
            await self._lock_sale(sale_id)
            seen: set[uuid.UUID] = set()
            for sale_item, _qty in group.requested:
                if sale_item.id in seen:
                    raise ValidationError(
                        "Duplicate sale line in delivery note",
                        field_errors={"lines": "Duplicate sale line"},
                    )
                seen.add(sale_item.id)

            allocated = await self.repo.allocated_by_sale_item(sale_id, exclude_note_id=exclude_note_id)
            sale_items = await self._sale_items(sale_id)
            ordered_by_item = {item.id: _q4(item.quantity - item.returned_quantity) for item in sale_items}
            for sale_item, qty in group.requested:
                ordered = ordered_by_item.get(sale_item.id)
                if ordered is None:
                    raise NotFoundError("Sale line does not belong to this sale")
                remaining = ordered - allocated.get(sale_item.id, Decimal("0"))
                if qty > remaining:
                    raise ValidationError(
                        f"Cannot deliver more than the remaining quantity ({remaining}) for {sale_item.product_name}",
                        field_errors={"lines": "Over-delivery rejected"},
                    )

    # ---------------------------------------------------------------- create

    async def create(self, payload, *, actor: User) -> DeliveryNote:
        # Group requested lines by parent sale; the POS shortcut may omit the
        # per-line sale_id (payload.sale_id applies to every line).
        groups: dict[uuid.UUID, _SaleGroup] = {}
        line_count = 0
        for line in payload.lines:
            sale_id = line.sale_id or payload.sale_id
            if sale_id is None:
                raise ValidationError(
                    "Every line needs its parent sale",
                    field_errors={"lines": "sale_id is required"},
                )
            group = groups.get(sale_id)
            if group is None:
                await self._lock_sale(sale_id)
                sale = await self._sale(sale_id)
                if sale.sale_status not in DELIVERABLE_SALE_STATUSES:
                    raise ConflictError("Delivery notes can only be created from completed sales")
                sale_items = {item.id: item for item in await self._sale_items(sale_id)}
                group = groups[sale_id] = _SaleGroup(sale, sale_items)
            sale_item = group.sale_items.get(line.sale_item_id)
            if sale_item is None:
                raise NotFoundError("Sale line does not belong to this sale")
            group.requested.append((sale_item, _q4(line.qty_to_deliver)))
            line_count += 1
        if line_count == 0:
            raise ValidationError(
                "Add at least one line with a quantity to deliver",
                field_errors={"lines": "Required"},
            )

        # All invoices on one delivery note must share the same customer.
        customer_ids = {group.sale.customer_id for group in groups.values()}
        if len(customer_ids) > 1:
            raise ValidationError(
                "All invoices on one delivery note must belong to the same customer",
                field_errors={"lines": "Mixed customers"},
            )
        customer_id = customer_ids.pop()
        if payload.customer_id is not None and str(payload.customer_id) != str(customer_id):
            raise ValidationError(
                "The selected customer does not match the invoices' customer",
                field_errors={"customer_id": "Customer mismatch"},
            )
        customer = await self.session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")

        await self._validate_lines(groups)

        delivery_no = await allocate_document_number(self.session, "DELIVERY_NOTE")
        note = DeliveryNote(
            delivery_no=delivery_no,
            customer_id=customer.id,
            # phone/location are NOT NULL (spec §2.1.9): caller value wins,
            # then the customer snapshot, then an empty string so the draft
            # can always be persisted and edited before Confirm.
            delivery_phone=payload.delivery_phone or customer.phone or "",
            delivery_location=payload.delivery_location or customer.address or "",
            status=DeliveryNote.STATUS_DRAFT,
            note=payload.note,
            created_by=actor.id,
        )
        for sale_id, group in groups.items():
            note.sales.append(DeliveryNoteSale(sale_id=sale_id, invoice_no=group.sale.invoice_no))
        self.repo.add(note)
        await self.repo.flush()
        for sale_id, group in groups.items():
            for sale_item, qty in group.requested:
                self.session.add(
                    DeliveryNoteItem(
                        delivery_note_id=note.id,
                        sale_id=sale_id,
                        sale_item_id=sale_item.id,
                        product_id=sale_item.product_id,
                        product_name=sale_item.product_name,
                        uom_symbol=sale_item.uom_symbol,
                        # qty_ordered is the original sale-line quantity (spec section 2.1.9).
                        qty_ordered=_q4(sale_item.quantity),
                        qty_to_deliver=qty,
                        qty_delivered=Decimal("0"),
                    )
                )

        if payload.confirm:
            await self._transition(note, DeliveryNote.STATUS_CONFIRMED, actor=actor)
        else:
            await record_audit(
                self.session,
                action="delivery_created",
                module="delivery",
                user_id=actor.id,
                entity_type="delivery_note",
                entity_id=note.id,
                new_values={
                    "delivery_no": note.delivery_no,
                    "invoice_nos": [link.invoice_no for link in note.sales],
                },
            )
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def create_from_sale(self, sale_id: uuid.UUID, payload, *, actor: User) -> DeliveryNote:
        """POS auto-entry (POST /pos/sales/{id}/delivery-notes): prefill one
        delivery note from a single sale. Default lines = every sale line with
        remaining undelivered qty; phone/location default from the customer.
        Reuses the canonical create() so all same-customer / allocation rules
        apply."""
        await self._lock_sale(sale_id)
        sale = await self._sale(sale_id)
        if sale.sale_status not in DELIVERABLE_SALE_STATUSES:
            raise ConflictError("Delivery notes can only be created from completed sales")

        sale_items = await self._sale_items(sale_id)
        allocated = await self.repo.allocated_by_sale_item(sale_id)

        requested: dict[uuid.UUID, Decimal] = {}
        override_lines = getattr(payload, "lines", None)
        if override_lines:
            for line in override_lines:
                if line.sale_id is not None and str(line.sale_id) != str(sale_id):
                    raise ValidationError(
                        "Lines must belong to the selected sale",
                        field_errors={"lines": "Sale mismatch"},
                    )
                if line.sale_item_id in requested:
                    raise ValidationError(
                        "Duplicate sale line in delivery note",
                        field_errors={"lines": "Duplicate sale line"},
                    )
                requested[line.sale_item_id] = _q4(line.qty_to_deliver)
        else:
            for item in sale_items:
                remaining = _q4(item.quantity - item.returned_quantity) - allocated.get(item.id, Decimal("0"))
                if remaining > 0:
                    requested[item.id] = remaining
        if not requested:
            raise ConflictError("This sale has no remaining quantity to deliver")

        create_payload = DeliveryNoteCreate(
            sale_id=sale_id,
            customer_id=sale.customer_id,
            delivery_phone=getattr(payload, "delivery_phone", None),
            delivery_location=getattr(payload, "delivery_location", None),
            note=getattr(payload, "note", None),
            confirm=bool(getattr(payload, "confirm", False)),
            lines=[
                DeliveryNoteLineCreate(sale_id=sale_id, sale_item_id=item_id, qty_to_deliver=qty)
                for item_id, qty in requested.items()
            ],
        )
        return await self.create(create_payload, actor=actor)

    # ------------------------------------------------------------------ edit

    async def update_draft(self, delivery_note_id: uuid.UUID, payload) -> DeliveryNote:
        note = await self.get(delivery_note_id)
        if note.status != DeliveryNote.STATUS_DRAFT:
            raise ConflictError("Only draft delivery notes can be edited")

        if payload.lines is not None:
            groups: dict[uuid.UUID, _SaleGroup] = {}
            for line in payload.lines:
                if line.sale_id is None:
                    raise ValidationError(
                        "Every line needs its parent sale",
                        field_errors={"lines": "sale_id is required"},
                    )
                group = groups.get(line.sale_id)
                if group is None:
                    await self._lock_sale(line.sale_id)
                    sale = await self._sale(line.sale_id)
                    if sale.customer_id != note.customer_id:
                        raise ValidationError(
                            "All invoices on one delivery note must belong to the same customer",
                            field_errors={"lines": "Mixed customers"},
                        )
                    sale_items = {item.id: item for item in await self._sale_items(line.sale_id)}
                    group = groups[line.sale_id] = _SaleGroup(sale, sale_items)
                sale_item = group.sale_items.get(line.sale_item_id)
                if sale_item is None:
                    raise NotFoundError("Sale line does not belong to this sale")
                group.requested.append((sale_item, _q4(line.qty_to_deliver)))

            await self._validate_lines(groups, exclude_note_id=note.id)

            note.items.clear()
            note.sales.clear()
            await self.session.flush()
            for sale_id, group in groups.items():
                note.sales.append(DeliveryNoteSale(sale_id=sale_id, invoice_no=group.sale.invoice_no))
                for sale_item, qty in group.requested:
                    self.session.add(
                        DeliveryNoteItem(
                            delivery_note_id=note.id,
                            sale_id=sale_id,
                            sale_item_id=sale_item.id,
                            product_id=sale_item.product_id,
                            product_name=sale_item.product_name,
                            uom_symbol=sale_item.uom_symbol,
                            qty_ordered=_q4(sale_item.quantity),
                            qty_to_deliver=qty,
                            qty_delivered=Decimal("0"),
                        )
                    )

        for field in ("delivery_phone", "delivery_location", "note"):
            value = getattr(payload, field)
            if value is not None:
                setattr(note, field, value)
        await self.repo.flush()
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    # ------------------------------------------------------------ transitions

    async def set_status(self, delivery_note_id: uuid.UUID, payload, *, actor: User) -> DeliveryNote:
        """Unified Update Status endpoint (spec §5.13)."""
        note = await self.get(delivery_note_id)
        target = payload.status
        if target is None:
            raise ValidationError(
                "A target status is required",
                field_errors={"status": "Required"},
            )
        reason = payload.cancel_reason
        await self._transition(note, target, actor=actor, reason=reason)
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def confirm(self, delivery_note_id: uuid.UUID, *, actor: User) -> DeliveryNote:
        note = await self.get(delivery_note_id)
        await self._transition(note, DeliveryNote.STATUS_CONFIRMED, actor=actor)
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def out_for_delivery(self, delivery_note_id: uuid.UUID, *, actor: User) -> DeliveryNote:
        note = await self.get(delivery_note_id)
        await self._transition(note, DeliveryNote.STATUS_OUT_FOR_DELIVERY, actor=actor)
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def deliver(self, delivery_note_id: uuid.UUID, *, actor: User) -> DeliveryNote:
        note = await self.get(delivery_note_id)
        await self._transition(note, DeliveryNote.STATUS_DELIVERED, actor=actor)
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def cancel(self, delivery_note_id: uuid.UUID, payload, *, actor: User) -> DeliveryNote:
        note = await self.get(delivery_note_id)
        reason = getattr(payload, "reason", None) or getattr(payload, "cancel_reason", None)
        await self._transition(note, DeliveryNote.STATUS_CANCELLED, actor=actor, reason=reason)
        await self.session.commit()
        await self.session.refresh(note, attribute_names=["items", "sales"])
        return note

    async def _transition(
        self,
        note: DeliveryNote,
        target: str,
        *,
        actor: User,
        reason: str | None = None,
    ) -> None:
        old_status = note.status
        if target not in ALLOWED_TRANSITIONS.get(old_status, set()):
            raise ConflictError(f"Cannot move a {old_status} delivery note to {target}")

        if target == DeliveryNote.STATUS_CANCELLED:
            if not (reason or "").strip():
                raise ValidationError(
                    "A reason is required to cancel a delivery note",
                    field_errors={"cancel_reason": "Required"},
                )
        else:
            # Phone + location are required for Confirm / Out for Delivery /
            # Delivered (editable header inputs — spec §2.1.9).
            if not (note.delivery_phone or "").strip() or not (note.delivery_location or "").strip():
                raise ValidationError(
                    "Phone and location are required before confirming or delivering",
                    field_errors={"delivery_phone": "Required"},
                )

        note.status = target
        if target == DeliveryNote.STATUS_CANCELLED:
            note.cancel_reason = reason
        if target == DeliveryNote.STATUS_DELIVERED:
            note.delivered_at = note.delivered_at or datetime.now(timezone.utc)
            for item in note.items:
                item.qty_delivered = item.qty_to_deliver
        await self.repo.flush()
        await record_audit(
            self.session,
            action=STATUS_TRANSITION_AUDIT_ACTION[target],
            module="delivery",
            user_id=actor.id,
            entity_type="delivery_note",
            entity_id=note.id,
            old_values={"status": old_status},
            new_values={
                "delivery_no": note.delivery_no,
                "status": target,
                "reason": reason,
                **(
                    {"delivered_at": note.delivered_at.isoformat()}
                    if target == DeliveryNote.STATUS_DELIVERED
                    else {}
                ),
            },
        )

    # ------------------------------------------------------------------ reads

    async def get(self, delivery_note_id: uuid.UUID) -> DeliveryNote:
        note = await self.repo.get(delivery_note_id)
        if note is None:
            raise NotFoundError("Delivery note not found")
        return note

    async def list(self, *, q, status, customer_id, start, end, page, limit) -> tuple[list[DeliveryNote], int]:
        return await self.repo.list(
            q=q,
            status=status,
            customer_id=customer_id,
            sale_id=None,
            start=start,
            end=end,
            page=page,
            limit=limit,
        )

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[DeliveryNote]:
        customer = await self.session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        notes, _total = await self.repo.list(
            q=None,
            status=None,
            customer_id=customer_id,
            sale_id=None,
            start=None,
            end=None,
            page=1,
            limit=1000,
        )
        return notes

    async def customer_name(self, note: DeliveryNote) -> str | None:
        customer = await self.session.get(Customer, note.customer_id)
        return customer.name if customer else None


def note_to_out(note: DeliveryNote, customer_name: str | None = None) -> DeliveryNoteOut:
    sales = sorted(
        (DeliveryNoteSaleOut(sale_id=link.sale_id, invoice_no=link.invoice_no) for link in note.sales),
        key=lambda link: link.invoice_no,
    )
    invoice_nos = [link.invoice_no for link in sales]
    return DeliveryNoteOut(
        id=note.id,
        delivery_no=note.delivery_no,
        customer_id=note.customer_id,
        customer_name=customer_name,
        sales=sales,
        invoice_nos=invoice_nos,
        invoiceNo=invoice_nos,
        invoice_no=", ".join(invoice_nos),
        delivery_phone=note.delivery_phone,
        deliveryPhone=note.delivery_phone,
        delivery_location=note.delivery_location,
        deliveryLocation=note.delivery_location,
        delivered_at=note.delivered_at,
        deliveredAt=note.delivered_at,
        status=note.status,
        note=note.note,
        cancel_reason=note.cancel_reason,
        created_by=note.created_by,
        created_at=note.created_at,
        items_count=len(note.items),
        items=[DeliveryNoteItemOut.model_validate(item) for item in note.items],
    )
