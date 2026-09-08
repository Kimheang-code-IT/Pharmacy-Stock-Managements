from uuid import UUID

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ListParams,
    envelope,
    get_db_session,
    list_params,
    require_permission,
)
from app.modules.auth.models import User
from app.modules.delivery_notes.schemas import (
    DeliveryNoteCancelRequest,
    DeliveryNoteCreate,
    DeliveryNoteStatusRequest,
    DeliveryNoteUpdate,
)
from app.modules.delivery_notes.service import (
    ACTION_TO_STATUS,
    DeliveryNoteService,
    note_to_out,
)

# Delivery Notes are fulfillment tracking only (spec section 2.1.9). No stock
# mutation happens anywhere in this module. Routes use flat business ownership
# under /api/v1; cross-module entry points (sales/customers/pos) are declared
# here so the workflow stays in one module.
router = APIRouter(tags=["delivery-notes"])


@router.get("/delivery-notes")
async def list_delivery_notes(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    service = DeliveryNoteService(db)
    notes, total = await service.list(
        q=params.q,
        status=params.status,
        customer_id=customer_id,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    data = [note_to_out(n, await service.customer_name(n)) for n in notes]
    return envelope(data, {"page": params.page, "limit": params.limit, "total": total})


@router.post("/delivery-notes", status_code=http_status.HTTP_201_CREATED)
async def create_delivery_note(
    payload: DeliveryNoteCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.create")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.create(payload, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.get("/delivery-notes/deliverable-invoices")
async def list_deliverable_invoices(
    search: str | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Confirmed sales with remaining deliverable qty (create-page invoice
    picker: live search by invoice no, customer secondary; multi-select)."""
    service = DeliveryNoteService(db)
    data = await service.deliverable_invoices(q=search, customer_id=customer_id)
    return envelope([row.model_dump(mode="json") for row in data])


@router.get("/delivery-notes/{delivery_note_id}")
async def get_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.get(delivery_note_id)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.patch("/delivery-notes/{delivery_note_id}")
async def update_delivery_note(
    delivery_note_id: UUID,
    payload: DeliveryNoteUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.update")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.update_draft(delivery_note_id, payload)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.post("/delivery-notes/{delivery_note_id}/confirm")
async def confirm_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.confirm")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.confirm(delivery_note_id, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.post("/delivery-notes/{delivery_note_id}/out-for-delivery")
async def delivery_note_out_for_delivery(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.confirm")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.out_for_delivery(delivery_note_id, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.post("/delivery-notes/{delivery_note_id}/deliver")
async def deliver_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.deliver")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.deliver(delivery_note_id, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.post("/delivery-notes/{delivery_note_id}/cancel")
async def cancel_delivery_note(
    delivery_note_id: UUID,
    payload: DeliveryNoteCancelRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.cancel")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.cancel(delivery_note_id, payload, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.post("/delivery-notes/{delivery_note_id}/status")
async def set_delivery_note_status(
    delivery_note_id: UUID,
    payload: DeliveryNoteStatusRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Unified Update Status endpoint (spec §2.1.9 transition table):
    {"status": "CONFIRMED|OUT_FOR_DELIVERY|DELIVERED|CANCELLED",
    "cancel_reason"?: "..."}. The legacy verb aliases (confirm /
    out_for_delivery / deliver / cancel) map to the same transition service,
    which still enforces the server-side permission for each target."""
    service = DeliveryNoteService(db)
    target = payload.status
    if target is None:
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "A target status is required",
            field_errors={"status": "Required"},
        )
    if target in ACTION_TO_STATUS:  # legacy verb alias → status
        target = ACTION_TO_STATUS[target]
    if target == "CONFIRMED":
        await _require(actor, "delivery.confirm")
    elif target == "OUT_FOR_DELIVERY":
        await _require(actor, "delivery.confirm")
    elif target == "DELIVERED":
        await _require(actor, "delivery.deliver")
    elif target == "CANCELLED":
        await _require(actor, "delivery.cancel")
        if not (payload.cancel_reason or "").strip():
            from app.core.exceptions import ValidationError

            raise ValidationError(
                "A reason is required to cancel a delivery note",
                field_errors={"cancel_reason": "Required"},
            )
    note = await service.set_status(
        delivery_note_id,
        DeliveryNoteStatusRequest(status=target, cancel_reason=payload.cancel_reason),
        actor=actor,
    )
    return envelope(note_to_out(note, await service.customer_name(note)))


async def _require(actor: User, permission: str) -> None:
    from app.core.permissions import user_has_permission

    if not user_has_permission(actor, permission):
        from app.core.exceptions import AccessDeniedError

        raise AccessDeniedError()


@router.get("/delivery-notes/{delivery_note_id}/print")
async def print_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Structured print payload (document header, lines, signature blocks)."""
    service = DeliveryNoteService(db)
    note = await service.get(delivery_note_id)
    customer_name = await service.customer_name(note)
    return envelope(
        {
            "document_title": "Delivery Note",
            "delivery_no": note.delivery_no,
            "invoice_nos": [link.invoice_no for link in note.sales],
            "status": note.status,
            "customer_name": customer_name,
            "delivery_phone": note.delivery_phone,
            "delivery_location": note.delivery_location,
            "delivered_at": note.delivered_at,
            "note": note.note,
            "lines": [
                {
                    "invoice_no": next(
                        (
                            link.invoice_no
                            for link in note.sales
                            if link.sale_id == item.sale_id
                        ),
                        "",
                    ),
                    "product_name": item.product_name,
                    "uom_symbol": item.uom_symbol,
                    "qty_ordered": item.qty_ordered,
                    "qty_to_deliver": item.qty_to_deliver,
                    "qty_delivered": item.qty_delivered,
                }
                for item in note.items
            ],
            "signature_blocks": ["Receiver", "Delivery staff"],
        }
    )


# --------------------------------------------------- sale-linked entry points


@router.get("/sales/{sale_id}/deliverable-items")
async def sale_deliverable_items(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Remaining-to-deliver quantities per sale line (drives the create form)."""
    service = DeliveryNoteService(db)
    return envelope(await service.deliverable_items(sale_id))


@router.post("/pos/sales/{sale_id}/delivery-notes", status_code=http_status.HTTP_201_CREATED)
async def create_delivery_note_from_pos_sale(
    sale_id: UUID,
    payload: DeliveryNoteCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.create")),
) -> dict:
    """POS post-sale 'Create Delivery Note' entry point."""
    service = DeliveryNoteService(db)
    payload.sale_id = sale_id
    note = await service.create(payload, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.get("/customers/{customer_id}/delivery-notes")
async def customer_delivery_notes(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Delivery notes related to a customer (customer detail view)."""
    service = DeliveryNoteService(db)
    notes = await service.list_for_customer(customer_id)
    return envelope([note_to_out(n, await service.customer_name(n)) for n in notes])
