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
from app.modules.delivery_notes.schemas import DeliveryNoteFromSaleCreate
from app.modules.pos.schemas import (
    SaleCreateRequest,
    SaleReturnRequest,
)
from app.modules.pos.service import POSService, sale_to_out

router = APIRouter(prefix="/pos", tags=["pos"])


@router.get("/products/search")
async def search_products(
    q: str | None = Query(default=None, max_length=100),
    category_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    return envelope(await service.search_products(q=q, category_id=category_id, limit=limit))


@router.get("/products/barcode/{barcode}")
async def product_by_barcode(
    barcode: str,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    return envelope(await service.product_by_barcode(barcode))


@router.get("/sales")
async def list_sales(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    sales, total = await service.list_sales(
        q=params.q,
        customer_id=customer_id,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [sale_to_out(s) for s in sales], {"page": params.page, "limit": params.limit, "total": total}
    )


@router.post("/sales", status_code=http_status.HTTP_201_CREATED)
async def complete_sale(
    payload: SaleCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    return envelope(await service.complete_sale(payload, actor=actor))


@router.post("/sales/complete", status_code=http_status.HTTP_201_CREATED)
async def complete_sale_alias(
    payload: SaleCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    """Alias of POST /pos/sales — the endpoint the frontend calls."""
    service = POSService(db)
    return envelope(await service.complete_sale(payload, actor=actor))


@router.get("/sales/{sale_id}")
async def get_sale(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    return envelope(sale_to_out(await service.get_sale(sale_id)))


@router.post("/sales/{sale_id}/return", status_code=http_status.HTTP_201_CREATED)
async def return_sale(
    sale_id: UUID,
    payload: SaleReturnRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    service = POSService(db)
    return envelope(await service.return_sale(sale_id, payload, actor=actor))


@router.post("/sales/{sale_id}/delivery-notes", status_code=http_status.HTTP_201_CREATED)
async def create_delivery_note_from_sale(
    sale_id: UUID,
    payload: DeliveryNoteFromSaleCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("delivery.create")),
) -> dict:
    """POS auto-entry: prefill/create a delivery note from ONE sale (spec
    §2.1.9). Default lines = every sale line's remaining undelivered qty;
    phone/location default from the customer. Delegates to the canonical
    delivery-note create transaction (no stock movement)."""
    from app.modules.delivery_notes.service import DeliveryNoteService, note_to_out

    service = DeliveryNoteService(db)
    note = await service.create_from_sale(sale_id, payload, actor=actor)
    return envelope(note_to_out(note, await service.customer_name(note)))


@router.get("/sales/{sale_id}/receipt")
async def sale_receipt(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.access")),
) -> dict:
    """Print-ready bilingual invoice payload (shop, invoice, lines with UOM,
    totals, payment). The frontend prints HTML — this JSON drives the paper."""
    service = POSService(db)
    sale = await service.get_sale(sale_id)
    return envelope(await service.build_receipt(sale))


@router.get("/sales/{sale_id}/invoice.pdf")
async def sale_invoice_pdf(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("pos.print")),
):
    """Archived invoice PDF: streams the stored object when it exists, otherwise
    renders and archives it first (object key is kept on the sale row)."""
    from fastapi import Response

    service = POSService(db)
    sale = await service.get_sale(sale_id)
    content = await service.get_or_generate_invoice_pdf(sale)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{sale.invoice_no}.pdf"'},
    )
