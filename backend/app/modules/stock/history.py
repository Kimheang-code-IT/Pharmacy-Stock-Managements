"""Product stock-history read model — spec section 2.1.5.

Clicking Stock In / Stock Out / Damage / Current Stock on the Stock list opens
a history dialog filtered to that product and movement kind. Rows are compact:
date, type, product, unit, unit price, qty, reference, user, note.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.stock.models import StockMovement
from app.shared.pagination.params import parse_date_range

# kind -> movement types. Every canonical movement type maps to exactly one
# dialog kind so the Stock list columns and the dialogs always agree:
# Stock In = STOCK_IN + SALE_RETURN, Stock Out = SALE + PURCHASE_RETURN,
# Damage = DAMAGE only (Expiry is a separate operation and is never folded
# into Damage).
MOVEMENT_KINDS: dict[str, tuple[str, ...]] = {
    "stock_in": ("STOCK_IN", "SALE_RETURN"),
    "stock_out": ("SALE", "PURCHASE_RETURN"),
    "damage": ("DAMAGE",),
    "all": (),  # empty tuple = no type filter (full movement history)
}


def movement_kind_types(kind: str | None) -> tuple[str, ...]:
    """Resolve a history-dialog kind filter to movement types."""
    normalized = (kind or "all").strip().lower()
    if normalized not in MOVEMENT_KINDS:
        raise ValueError(f"Unknown history kind '{kind}'")
    return MOVEMENT_KINDS[normalized]


def movement_kind(movement_type: str) -> str:
    """Map a movement type back to its dialog kind."""
    for kind, types in MOVEMENT_KINDS.items():
        if movement_type in types:
            return kind
    return "all"


def _display_type(movement_type: str) -> str:
    """Labels the Stock list dialogs already filter on:
    Stock In / Sale Return / Sale / Damage."""
    return movement_type.replace("_", " ").title()


async def product_history(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    kind: str | None,
    start: str | None,
    end: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Compact, paginated stock-history rows for one product."""
    movement_types = movement_kind_types(kind)

    conditions = [StockMovement.product_id == product_id]
    if movement_types:
        conditions.append(StockMovement.movement_type.in_(movement_types))
    start_at, end_at = parse_date_range(start, end)
    if start_at is not None:
        conditions.append(StockMovement.created_at >= start_at)
    if end_at is not None:
        conditions.append(StockMovement.created_at <= end_at)

    count_stmt = select(func.count()).select_from(StockMovement).where(*conditions)
    total = (await session.execute(count_stmt)).scalar_one()

    rows = await session.execute(
        select(StockMovement, User.full_name)
        .join(User, User.id == StockMovement.created_by, isouter=True)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )

    history: list[dict] = []
    for movement, user_name in rows.all():
        product = movement.product_ref
        history.append(
            {
                "id": movement.id,
                "date": movement.created_at,
                "type": _display_type(movement.movement_type),
                "kind": movement_kind(movement.movement_type),
                "qty": movement.quantity_delta,
                "product": movement.product_name or (product.name if product else ""),
                "unit": movement.uom_symbol
                or (product.uom_ref.symbol if product and product.uom_ref else None),
                "unit_price": movement.unit_cost,
                "reference": movement.document_no,
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id,
                # Batch traceability (single-batch movements; multi-batch
                # outflows expose their lots through the allocation rows).
                "batch_no": movement.batch_no,
                "batch_id": movement.batch_id,
                "expiry_date": movement.expiry_date,
                "user": user_name,
                "note": movement.note,
            }
        )
    return history, int(total)


async def movement_invoice(session: AsyncSession, movement_id: uuid.UUID) -> dict:
    """Read-only invoice detail behind one SALE movement (Stock Out dialog).

    Reuses the POS receipt payload so the dialog and the printed invoice can
    never disagree. Movements that are not a POS sale (Stock In, Purchase
    Return, Damage, …) have no invoice and are rejected.
    """
    movement = await session.get(StockMovement, movement_id)
    if movement is None:
        raise NotFoundError("Stock movement not found")
    if movement.reference_type != "sale":
        raise ValidationError("This stock movement is not linked to a sale invoice")

    from app.modules.pos.models import Sale
    from app.modules.pos.service import POSService

    sale = await session.get(Sale, movement.reference_id)
    if sale is None:
        raise NotFoundError("Sale not found for this stock movement")
    return await POSService(session).build_receipt(sale)


async def product_batches(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    status: str | None,
    q: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Read-only batch lots for one product (product detail Batches tab).

    Rows mirror ``batch_stock_balances`` plus purchase metadata from the
    opening Stock In document and the active batch-scoped sale price (so the
    Batch tab can show purchase date / UOM / currency / sale price and toggle
    Pricing active without leaving the product document).
    """

    from app.modules.stock.batch_service import business_today
    from app.modules.stock.models import (
        BatchStockBalance,
        ProductSalePrice,
        StockTransaction,
        StockTransactionItem,
    )
    from app.modules.stock.repository import ProductRepository
    from app.modules.suppliers.models import Supplier
    from app.modules.uoms.models import UOM

    product = await ProductRepository(session).get(product_id)
    if product is None:
        raise NotFoundError("Product not found")

    base_uom_symbol = None
    if product.uom_id is not None:
        uom = await session.get(UOM, product.uom_id)
        if uom is not None:
            base_uom_symbol = uom.symbol or uom.name

    conditions = [BatchStockBalance.product_id == product_id]
    normalized = (status or "").strip().upper()
    if normalized and normalized != "ALL":
        today = await business_today(session)
        if normalized == "ACTIVE":
            conditions.append(BatchStockBalance.remaining_quantity > 0)
            conditions.append(
                (BatchStockBalance.expiry_date.is_(None))
                | (BatchStockBalance.expiry_date >= today)
            )
        elif normalized == "EXPIRED":
            conditions.append(BatchStockBalance.remaining_quantity > 0)
            conditions.append(
                BatchStockBalance.expiry_date.is_not(None)
                & (BatchStockBalance.expiry_date < today)
            )
        elif normalized == "DEPLETED":
            conditions.append(BatchStockBalance.remaining_quantity <= 0)
        else:
            raise ValidationError(f"Unknown batch status '{status}'")
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(BatchStockBalance.batch_no.ilike(pattern))

    count_stmt = select(func.count()).select_from(BatchStockBalance).where(*conditions)
    total = (await session.execute(count_stmt)).scalar_one()

    rows = await session.execute(
        select(BatchStockBalance, Supplier.name)
        .join(Supplier, Supplier.id == BatchStockBalance.supplier_id, isouter=True)
        .where(*conditions)
        .order_by(
            BatchStockBalance.expiry_date.asc().nulls_last(),
            BatchStockBalance.created_at.asc(),
            BatchStockBalance.batch_no.asc(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    today = await business_today(session)
    batch_rows = list(rows.all())

    # Opening purchase metadata keyed by document_no (transaction date + currency).
    document_nos = {
        str(batch.document_no).strip()
        for batch, _ in batch_rows
        if batch.document_no
    }
    purchase_by_doc: dict[str, tuple[object, str]] = {}
    if document_nos:
        tx_rows = await session.execute(
            select(StockTransaction).where(StockTransaction.document_no.in_(document_nos))
        )
        for tx in tx_rows.scalars().all():
            purchase_by_doc[str(tx.document_no)] = (tx.transaction_date, str(tx.currency or "USD"))

    # Purchase-line UOM for each (product, batch_no, expiry) from STOCK_IN lines.
    batch_nos = [str(batch.batch_no) for batch, _ in batch_rows]
    purchase_uom_by_lot: dict[tuple[str, object], str] = {}
    if batch_nos:
        item_rows = await session.execute(
            select(
                StockTransactionItem.batch_no,
                StockTransactionItem.expiry_date,
                StockTransactionItem.uom_symbol,
                StockTransactionItem.entered_uom_symbol,
                StockTransaction.transaction_date,
            )
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .where(
                StockTransactionItem.product_id == product_id,
                StockTransactionItem.batch_no.in_(batch_nos),
                StockTransaction.transaction_type == "STOCK_IN",
            )
            .order_by(StockTransaction.transaction_date.asc())
        )
        for batch_no, expiry, uom_symbol, entered_uom, _tx_date in item_rows.all():
            key = (str(batch_no or "").strip(), expiry)
            if not key[0] or key in purchase_uom_by_lot:
                continue
            purchase_uom_by_lot[key] = str(entered_uom or uom_symbol or base_uom_symbol or "")

    # Active sale-price versions scoped to these batches (+ general fallback).
    price_rows = await session.execute(
        select(ProductSalePrice).where(
            ProductSalePrice.product_id == product_id,
            ProductSalePrice.is_active.is_(True),
        )
    )
    active_by_batch: dict[str, ProductSalePrice] = {}
    general_price: ProductSalePrice | None = None
    for price in price_rows.scalars().all():
        scope = str(price.batch_no or "").strip()
        if not scope:
            general_price = price
        else:
            active_by_batch[scope] = price

    # Latest (any) version per batch for deactivate / reactivate when inactive.
    latest_rows = await session.execute(
        select(ProductSalePrice)
        .where(
            ProductSalePrice.product_id == product_id,
            ProductSalePrice.batch_no.is_not(None),
        )
        .order_by(ProductSalePrice.version.desc())
    )
    latest_by_batch: dict[str, ProductSalePrice] = {}
    for price in latest_rows.scalars().all():
        scope = str(price.batch_no or "").strip()
        if scope and scope not in latest_by_batch:
            latest_by_batch[scope] = price

    batches: list[dict] = []
    for batch, supplier_name in batch_rows:
        remaining = batch.remaining_quantity
        expiry = batch.expiry_date
        if remaining <= 0:
            computed_status = "DEPLETED"
        elif expiry is not None and expiry < today:
            computed_status = "EXPIRED"
        else:
            computed_status = "ACTIVE"

        doc_no = str(batch.document_no or "").strip()
        purchase_meta = purchase_by_doc.get(doc_no)
        purchase_date = None
        currency = "USD"
        if purchase_meta is not None:
            tx_date, currency = purchase_meta
            if hasattr(tx_date, "date"):
                purchase_date = tx_date.date()
            else:
                purchase_date = tx_date
        elif batch.created_at is not None:
            purchase_date = batch.created_at.date() if hasattr(batch.created_at, "date") else batch.created_at

        batch_key = str(batch.batch_no)
        active_price = active_by_batch.get(batch_key)
        latest_price = active_price or latest_by_batch.get(batch_key)
        pricing_active = active_price is not None
        if active_price is not None:
            sale_price = active_price.sale_price
            sale_price_id = active_price.id
        elif latest_price is not None:
            sale_price = latest_price.sale_price
            sale_price_id = latest_price.id
        elif general_price is not None:
            sale_price = general_price.sale_price
            sale_price_id = None
        else:
            sale_price = product.selling_price
            sale_price_id = None

        batches.append(
            {
                "id": batch.id,
                "product_id": batch.product_id,
                "batch_no": batch.batch_no,
                "expiry_date": expiry,
                "received_quantity": batch.received_quantity,
                "remaining_quantity": remaining,
                "unit_cost": batch.unit_cost,
                "supplier_id": batch.supplier_id,
                "supplier": supplier_name,
                "document_no": batch.document_no,
                "created_at": batch.created_at,
                "status": computed_status,
                # Manual sellable flag: inactive lots are excluded from POS FEFO.
                "is_active": batch.is_active,
                "isActive": batch.is_active,
                "purchase_date": purchase_date,
                "purchase_uom": purchase_uom_by_lot.get((batch_key, expiry)) or base_uom_symbol,
                "currency": currency,
                "sale_price": sale_price,
                "sale_price_id": sale_price_id,
                "pricing_active": pricing_active,
            }
        )
    return batches, int(total)
