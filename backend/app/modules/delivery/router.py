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
from app.modules.delivery.models import DeliveryNote
from app.modules.delivery.schemas import (
    DeliveryNoteCancelRequest,
    DeliveryNoteCreate,
    DeliveryNoteStatusRequest,
    DeliveryNoteUpdate,
)
from app.modules.delivery.service import (
    ACTION_TO_STATUS,
    LEGACY_STATUS_ALIASES,
    STATUS_PERMISSIONS,
    DeliveryNoteService,
    note_to_out,
)


async def _note_out(service: DeliveryNoteService, note) -> dict:
    """note_to_out + derived per-invoice delivery status (delivered qtys)."""
    sale_ids = [link.sale_id for link in note.sales]
    statuses = await service.invoice_delivery_statuses(sale_ids)
    sale_dates = await service.sale_dates(sale_ids)
    return note_to_out(note, await service.customer_name(note), statuses, sale_dates)

# Delivery Notes are fulfillment tracking only (spec section 2.1.9). No stock
# mutation happens anywhere in this module. Routes use flat business ownership
# under /api/v1; cross-module entry points (sales/customers/pos) are declared
# here so the workflow stays in one module.
router = APIRouter(tags=["delivery"])


@router.get("/delivery")
async def list_delivery_notes(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    from sqlalchemy import select

    from app.modules.customers.models import Customer

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
    # Batched list page: one status computation + one customer lookup (P2 N+1).
    all_sale_ids = [link.sale_id for note in notes for link in note.sales]
    statuses = await service.invoice_delivery_statuses(all_sale_ids)
    sale_dates = await service.sale_dates(all_sale_ids)
    customer_ids = {note.customer_id for note in notes}
    customer_names: dict = {}
    if customer_ids:
        result = await db.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
        )
        customer_names = {row_id: name for row_id, name in result.all()}
    data = [
        note_to_out(note, customer_names.get(note.customer_id), statuses, sale_dates)
        for note in notes
    ]
    return envelope(data, {"page": params.page, "limit": params.limit, "total": total})


@router.post("/delivery", status_code=http_status.HTTP_201_CREATED)
async def create_delivery_note(
    payload: DeliveryNoteCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.create")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.create(payload, actor=actor)
    return envelope(await _note_out(service, note))


@router.get("/delivery/deliverable-invoices")
async def list_deliverable_invoices(
    search: str | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    currency: str | None = Query(default=None, pattern="^(USD|KHR)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Confirmed sales with remaining deliverable qty (create-page invoice
    picker: live search by invoice no, customer secondary; multi-select).
    `currency` restricts the picker to one note currency."""
    service = DeliveryNoteService(db)
    data = await service.deliverable_invoices(q=search, customer_id=customer_id, currency=currency)
    return envelope([row.model_dump(mode="json") for row in data])


@router.get("/delivery/{delivery_note_id}")
async def get_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.get(delivery_note_id)
    return envelope(await _note_out(service, note))


@router.patch("/delivery/{delivery_note_id}")
async def update_delivery_note(
    delivery_note_id: UUID,
    payload: DeliveryNoteUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.update")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.update_draft(delivery_note_id, payload)
    return envelope(await _note_out(service, note))


@router.post("/delivery/{delivery_note_id}/confirm")
async def confirm_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.confirm")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.confirm(delivery_note_id, actor=actor)
    return envelope(await _note_out(service, note))


@router.post("/delivery/{delivery_note_id}/out-for-delivery")
async def delivery_note_out_for_delivery(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.confirm")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.out_for_delivery(delivery_note_id, actor=actor)
    return envelope(await _note_out(service, note))


@router.post("/delivery/{delivery_note_id}/deliver")
async def deliver_delivery_note(
    delivery_note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.deliver")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.deliver(delivery_note_id, actor=actor)
    return envelope(await _note_out(service, note))


@router.post("/delivery/{delivery_note_id}/cancel")
async def cancel_delivery_note(
    delivery_note_id: UUID,
    payload: DeliveryNoteCancelRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.cancel")),
) -> dict:
    service = DeliveryNoteService(db)
    note = await service.cancel(delivery_note_id, payload, actor=actor)
    return envelope(await _note_out(service, note))


@router.post("/delivery/{delivery_note_id}/status")
async def set_delivery_note_status(
    delivery_note_id: UUID,
    payload: DeliveryNoteStatusRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Unified Update Status endpoint (spec §2.1.9 extended transition table):
    {"status": "PREPARING|OUT_FOR_DELIVERY|PARTIALLY_DELIVERED|DELIVERED|FAILED|RETURNED",
    "cancel_reason"?: "..."}. Legacy aliases (CONFIRMED / CANCELLED and the
    verb forms confirm / out_for_delivery / deliver / cancel) map to the same
    transition service, which still enforces the server-side permission for
    each target."""
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
    target = LEGACY_STATUS_ALIASES.get(target, target)
    permission = STATUS_PERMISSIONS.get(target)
    if permission is None:
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "Unknown delivery status",
            field_errors={"status": "Unsupported status"},
        )
    await _require(actor, permission)
    if target in (DeliveryNote.STATUS_CANCELLED, DeliveryNote.STATUS_FAILED) and not (
        payload.cancel_reason or ""
    ).strip():
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "A reason is required to cancel or fail a delivery note",
            field_errors={"cancel_reason": "Required"},
        )
    note = await service.set_status(
        delivery_note_id,
        DeliveryNoteStatusRequest(status=target, cancel_reason=payload.cancel_reason),
        actor=actor,
    )
    return envelope(await _note_out(service, note))


async def _require(actor: User, permission: str) -> None:
    from app.core.permissions import user_has_permission

    if not user_has_permission(actor, permission):
        from app.core.exceptions import AccessDeniedError

        raise AccessDeniedError()


@router.get("/delivery/{delivery_note_id}/print")
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
            "driver_name": note.driver_name,
            "vehicle_no": note.vehicle_no,
            "delivery_date": note.delivery_date,
            "delivery_fee": note.delivery_fee,
            "received_by": note.received_by,
            "currency": note.currency,
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
                    "note": item.note,
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


@router.post("/pos/sales/{sale_id}/delivery", status_code=http_status.HTTP_201_CREATED)
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
    return envelope(await _note_out(service, note))


@router.get("/customers/{customer_id}/delivery")
async def customer_delivery_notes(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.view")),
) -> dict:
    """Delivery notes related to a customer (customer detail view)."""
    service = DeliveryNoteService(db)
    notes = await service.list_for_customer(customer_id)
    return envelope([await _note_out(service, n) for n in notes])
