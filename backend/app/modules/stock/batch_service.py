"""Canonical batch-stock service (spec: batch/expiry + multi-UOM + FEFO).

Responsibilities (never mixed, per the integration standard):

- Batch = physical inventory: expiry, remaining base quantity, cost, and
  supplier/purchase traceability.
- UOM = quantity conversion only (base qty = qty × factor_to_base); every
  factor is resolved from the product's Pricing rows server-side.
- Sale price = customer pricing (Product + UOM), never batch-dependent.

The product's `stock_balances` row stays the materialized total; this module
owns the per-batch ledger (`batch_stock_balances`) and the sale allocations
(`sale_item_batches`). All writes run under row locks inside the caller's
transaction. Batches without a batch_no/expiry (unbatched stock) are kept in
a single synthetic lot keyed on "" / NULL.

Expired lots (expiry_date < the configured business date) are NEVER allocated
to a sale; they can only leave stock through damage / expiry / purchase
return, which opt in with `include_expired=True`.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.modules.pos.models import SaleItemBatch
from app.modules.stock.models import BatchStockBalance, Product

FOUR = Decimal("0.0001")
TWO = Decimal("0.01")
SIX = Decimal("0.000001")
UNBATCHED_KEY = ""

BATCH_STATUS_ACTIVE = "ACTIVE"
BATCH_STATUS_DEPLETED = "DEPLETED"
BATCH_STATUS_EXPIRED = "EXPIRED"


def _q4(value) -> Decimal:
    return Decimal(value).quantize(FOUR, rounding=ROUND_HALF_UP)


def _q2(value) -> Decimal:
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def _q6(value) -> Decimal:
    return Decimal(value).quantize(SIX, rounding=ROUND_HALF_UP)


def _batch_key(batch_no: str | None) -> str:
    return (batch_no or "").strip()


def _bump_batch_no(base_no: str, taken: set[str]) -> str:
    """Next free batch number after `base_no`, incrementing its trailing digits
    (BATCH-001 → BATCH-002) or appending -1/-2 when it has no numeric suffix."""
    match = re.match(r"^(.*?)(\d+)$", base_no)
    if not match:
        seq = 1
        candidate = f"{base_no}-{seq}"
        while candidate in taken:
            seq += 1
            candidate = f"{base_no}-{seq}"
        return candidate
    prefix, digits = match.group(1), match.group(2)
    width = len(digits)
    seq = int(digits)
    candidate = base_no
    while candidate in taken:
        seq += 1
        candidate = f"{prefix}{str(seq).zfill(width)}"
    return candidate


async def _resolve_batch_no_for_new_lot(
    session: AsyncSession, product_id: uuid.UUID, batch_no: str | None, expiry_date
) -> str | None:
    """Auto-assign the next batch number when a batch_no is reused with a
    DIFFERENT expiry, so every lot carries its own batch number (and per-lot POS
    pricing stays unambiguous). An exact (batch_no, expiry) match, a brand-new
    batch_no, or an empty/unbatched batch_no is returned unchanged."""
    key = _batch_key(batch_no)
    if not key:
        return batch_no
    result = await session.execute(
        select(BatchStockBalance.batch_no, BatchStockBalance.expiry_date).where(
            BatchStockBalance.product_id == product_id
        )
    )
    rows = list(result.all())
    if any(str(existing) == key and expiry == expiry_date for existing, expiry in rows):
        return batch_no
    if not any(str(existing) == key for existing, _expiry in rows):
        return batch_no
    return _bump_batch_no(key, {str(existing) for existing, _expiry in rows})


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


async def business_today(session: AsyncSession) -> date:
    """Business date from the configured application timezone (settings
    `system.timezone`) — never the browser clock (spec: expired batch rule)."""
    from app.modules.administration import get_setting_value

    tz_name = await get_setting_value(session, "system", "timezone", "UTC")
    try:
        tz = ZoneInfo(str(tz_name) or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(timezone.utc).astimezone(tz).date()


def batch_status_of(batch: BatchStockBalance, today: date) -> str:
    """Lifecycle state of a lot: DEPLETED when exhausted, EXPIRED when its
    expiry date has passed with stock remaining, otherwise ACTIVE. Batches
    without an expiry date are never auto-marked EXPIRED."""
    if batch.remaining_quantity <= 0:
        return BATCH_STATUS_DEPLETED
    if batch.expiry_date is not None and batch.expiry_date < today:
        return BATCH_STATUS_EXPIRED
    return BATCH_STATUS_ACTIVE


def refresh_batch_status(batch: BatchStockBalance, today: date | None = None) -> None:
    """Keep the persisted lifecycle column in sync after a quantity change."""
    batch.status = batch_status_of(batch, today or _utc_today())


def factor_for_uom(product: Product, uom_id: str | None) -> Decimal:
    """Resolve factor_to_base server-side from the product's Pricing rows.

    The frontend factor is never authoritative: an explicit mismatch with the
    configured row raises, and an unknown UOM raises."""
    if uom_id is None or str(uom_id) == str(product.uom_id):
        return Decimal("1")
    for row in product.uom_conversions or []:
        if str(row.get("uom_id")) == str(uom_id):
            try:
                factor = Decimal(str(row.get("factor_to_base", 1)))
            except Exception as exc:
                raise ValidationError(
                    "Invalid conversion factor configured for this product",
                    field_errors={"uom_id": "Invalid factor"},
                ) from exc
            if factor <= 0:
                raise ValidationError(
                    "Conversion qty must be greater than zero",
                    field_errors={"uom_id": "Invalid factor"},
                )
            return factor
    raise ValidationError(
        "The selected UOM is not a Pricing UOM of this product",
        field_errors={"uom_id": "Invalid UOM"},
    )


def _lot_conditions(product_id: uuid.UUID, batch_no: str | None, expiry_date):
    """Exact lot key: (product_id, batch_no, expiry_date), NULL-safe on expiry."""
    conditions = [
        BatchStockBalance.product_id == product_id,
        BatchStockBalance.batch_no == _batch_key(batch_no),
    ]
    if expiry_date is None:
        conditions.append(BatchStockBalance.expiry_date.is_(None))
    else:
        conditions.append(BatchStockBalance.expiry_date == expiry_date)
    return conditions


async def _lock_batch(
    session: AsyncSession,
    product_id: uuid.UUID,
    batch_no: str | None,
    expiry_date=None,
) -> BatchStockBalance:
    """Fetch-or-create + row-lock the batch lot (identity = product + batch_no
    + expiry_date; a different expiry is a distinct lot)."""
    key = _batch_key(batch_no)
    conditions = _lot_conditions(product_id, batch_no, expiry_date)
    result = await session.execute(
        select(BatchStockBalance).where(*conditions).with_for_update()
    )
    batch = result.scalar_one_or_none()
    if batch is not None:
        return batch
    batch = BatchStockBalance(
        product_id=product_id,
        batch_no=key,
        expiry_date=expiry_date,
        received_quantity=Decimal("0"),
        remaining_quantity=Decimal("0"),
        unit_cost=Decimal("0.000000"),
        status=BATCH_STATUS_ACTIVE,
    )
    session.add(batch)
    try:
        # Savepoint so a concurrent creator losing the unique constraint race
        # does not poison the caller's transaction; we then use its row.
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        pass
    # Re-select under lock so a concurrent creator's row wins cleanly.
    result = await session.execute(
        select(BatchStockBalance)
        .where(*conditions)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def lock_batches_for_product(
    session: AsyncSession,
    product_id: uuid.UUID,
    *,
    include_expired: bool = False,
) -> list[BatchStockBalance]:
    """Locked remaining lots, FEFO order: NULL expiry last, then earliest
    expiry, then oldest receipt (deterministic secondary order). Caller must
    be inside a transaction; rows are locked FOR UPDATE so concurrent sales
    serialize per product.

    Sale-eligible lots exclude expired batches unless `include_expired` —
    disposals (damage / expiry / purchase return) opt in; sales never do."""
    conditions = [
        BatchStockBalance.product_id == product_id,
        BatchStockBalance.remaining_quantity > 0,
    ]
    if not include_expired:
        today = await business_today(session)
        conditions.append(
            (BatchStockBalance.expiry_date.is_(None))
            | (BatchStockBalance.expiry_date >= today)
        )
    result = await session.execute(
        select(BatchStockBalance)
        .where(*conditions)
        .order_by(
            BatchStockBalance.expiry_date.is_(None),
            BatchStockBalance.expiry_date.asc(),
            BatchStockBalance.created_at.asc(),
            BatchStockBalance.id.asc(),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def batch_in(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    batch_no: str | None,
    expiry_date: date | None,
    quantity_base,
    unit_cost_per_base,
    supplier_id=None,
    document_no: str | None = None,
) -> BatchStockBalance:
    """Add received base quantity to a batch lot (Stock In). The lot's
    unit_cost is the latest purchase's cost-per-base (the traceable purchase
    cost of that lot); expiry_date is stamped from the purchase when given.
    Historical costs stay on the immutable movement ledger."""
    quantity = _q4(quantity_base)
    if quantity <= 0:
        raise ValidationError("Batch received quantity must be greater than zero")
    # A batch_no reused with a different expiry gets the next batch number so
    # each lot is distinct (auto BATCH-001 → BATCH-002 → …).
    batch_no = await _resolve_batch_no_for_new_lot(session, product_id, batch_no, expiry_date)
    batch = await _lock_batch(session, product_id, batch_no, expiry_date)
    batch.remaining_quantity = _q4(batch.remaining_quantity + quantity)
    batch.received_quantity = _q4(batch.received_quantity + quantity)
    batch.unit_cost = _q6(unit_cost_per_base)
    if expiry_date is not None:
        batch.expiry_date = expiry_date
    batch.supplier_id = supplier_id or batch.supplier_id
    batch.document_no = document_no or batch.document_no
    refresh_batch_status(batch, await business_today(session))
    await session.flush()
    return batch


async def allocate_fefo(
    session: AsyncSession,
    *,
    product: Product,
    quantity_base,
    allow_negative: bool = False,
    include_expired: bool = False,
) -> list[tuple[BatchStockBalance, Decimal]]:
    """FEFO allocation for `quantity_base` units (already converted to base).

    Returns [(batch, taken_base)] rows whose SUM == quantity_base. Locks the
    batch rows; raises when availability is insufficient unless
    `allow_negative` (the same oversell gate as the canonical mutation).
    Expired lots are excluded unless `include_expired` (sales never consume
    them — spec: expired batch rule)."""
    needed = _q4(quantity_base)
    if needed <= 0:
        raise ValidationError("Sale quantity must be greater than zero")
    batches = await lock_batches_for_product(
        session, product.id, include_expired=include_expired
    )
    available = sum((batch.remaining_quantity for batch in batches), Decimal("0"))
    if needed > available and not allow_negative:
        raise ConflictError(
            f"Insufficient stock: available {available}, requested {needed}"
        )
    allocations: list[tuple[BatchStockBalance, Decimal]] = []
    remaining = needed
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_quantity, remaining)
        allocations.append((batch, _q4(take)))
        remaining -= take
    return allocations


async def deduct_allocations(
    session: AsyncSession, allocations: list[tuple[BatchStockBalance, Decimal]]
) -> None:
    """Apply FEFO allocations as an outflow: deduct each batch's remaining
    quantity and refresh its lifecycle status. Must run inside the caller's
    transaction (the rows are already locked by allocate_fefo)."""
    today = await business_today(session)
    for batch, amount in allocations:
        batch.remaining_quantity = _q4(batch.remaining_quantity - amount)
        refresh_batch_status(batch, today)
    await session.flush()


async def commit_sale_allocations(
    session: AsyncSession,
    *,
    sale_item,
    product: Product,
    quantity_base,
    allow_negative: bool = False,
) -> tuple[Decimal, list[BatchStockBalance]]:
    """Allocate FEFO, deduct batch rows, append SaleItemBatch rows.

    Returns (blended cost-per-base snapshot, consumed batch lots). The
    customer price is INDEPENDENT of batch cost; the blended cost is only the
    sale line's cost snapshot. Must run inside the sale transaction."""
    needed = _q4(quantity_base)
    allocations = await allocate_fefo(
        session, product=product, quantity_base=needed, allow_negative=allow_negative
    )
    today = await business_today(session)
    remaining = needed
    weighted = Decimal("0")
    taken = Decimal("0")
    consumed: list[BatchStockBalance] = []
    for batch, amount in allocations:
        batch.remaining_quantity = _q4(batch.remaining_quantity - amount)
        refresh_batch_status(batch, today)
        cost = _q6(batch.unit_cost)
        session.add(
            SaleItemBatch(
                sale_item_id=sale_item.id,
                batch_id=batch.id,
                quantity_base=amount,
                cost_per_base=cost,
            )
        )
        consumed.append(batch)
        remaining -= amount
        weighted += amount * cost
        taken += amount
    if remaining > 0:
        # Negative-stock shortfall beyond tracked batches: price the
        # remainder at the product's average cost; no batch row exists.
        fallback = _q2(product.balance.average_cost if product.balance else product.cost_price)
        weighted += remaining * fallback
        taken += remaining
    await session.flush()
    blended = (weighted / taken).quantize(TWO, rounding=ROUND_HALF_UP) if taken > 0 else Decimal("0.00")
    return blended, consumed


async def restore_sale_batches(
    session: AsyncSession,
    *,
    sale_item,
    quantity_base,
) -> None:
    """Return `quantity_base` units to the original sold batches, consumed
    newest-first (reverse FEFO so partially-consumed later lots refill
    first). Called by sale return when restock=True. Restoring into a lot
    whose expiry has passed is intentional: the lot can no longer be SOLD
    (FEFO excludes expired batches) — it waits for a damage/expiry/purchase-
    return write-down instead of silently becoming sellable stock."""
    remaining = _q4(quantity_base)
    if remaining <= 0:
        return
    result = await session.execute(
        select(SaleItemBatch)
        .where(SaleItemBatch.sale_item_id == sale_item.id)
        .order_by(SaleItemBatch.created_at.desc(), SaleItemBatch.id.desc())
    )
    allocations = list(result.scalars().all())
    if not allocations:
        return
    today = await business_today(session)
    restored: dict[uuid.UUID, BatchStockBalance] = {}
    for allocation in allocations:
        if remaining <= 0:
            break
        give_back = min(allocation.quantity_base, remaining)
        if give_back <= 0:
            continue
        batch = await session.get(
            BatchStockBalance,
            allocation.batch_id,
            with_for_update=True,
            populate_existing=True,
        )
        if batch is None:
            continue
        batch.remaining_quantity = _q4(batch.remaining_quantity + give_back)
        remaining -= give_back
        restored[batch.id] = batch
    for batch in restored.values():
        refresh_batch_status(batch, today)
    await session.flush()


async def deduct_from_batch(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    batch_no: str | None,
    quantity_base,
    expiry_date=None,
) -> BatchStockBalance:
    """Deduct `quantity_base` from a named batch (Damage / Expiry / Purchase
    Return / purchase edit on a batched line).

    When `expiry_date` is given the exact (product, batch_no, expiry) lot is
    used; otherwise the batch_no's lots are drained FEFO (oldest expiry first,
    expired included — disposals may write down expired lots). Returns the lot
    the movement links to (the first/oldest deducted lot)."""
    quantity = _q4(quantity_base)
    if quantity <= 0:
        raise ValidationError("Batch quantity must be greater than zero")
    if expiry_date is not None:
        batch = await _lock_batch(session, product_id, batch_no, expiry_date)
        if batch.remaining_quantity < quantity:
            raise ConflictError(
                f"Insufficient batch stock: available {batch.remaining_quantity}, requested {quantity}"
            )
        batch.remaining_quantity = _q4(batch.remaining_quantity - quantity)
        refresh_batch_status(batch, await business_today(session))
        await session.flush()
        return batch

    key = _batch_key(batch_no)
    result = await session.execute(
        select(BatchStockBalance)
        .where(
            BatchStockBalance.product_id == product_id,
            BatchStockBalance.batch_no == key,
            BatchStockBalance.remaining_quantity > 0,
        )
        .order_by(
            BatchStockBalance.expiry_date.is_(None),
            BatchStockBalance.expiry_date.asc(),
            BatchStockBalance.created_at.asc(),
            BatchStockBalance.id.asc(),
        )
        .with_for_update()
    )
    lots = list(result.scalars().all())
    available = sum((lot.remaining_quantity for lot in lots), Decimal("0"))
    if available < quantity:
        raise ConflictError(
            f"Insufficient batch stock: available {available}, requested {quantity}"
        )
    today = await business_today(session)
    remaining = quantity
    primary = lots[0]
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.remaining_quantity, remaining)
        lot.remaining_quantity = _q4(lot.remaining_quantity - take)
        refresh_batch_status(lot, today)
        remaining -= take
    await session.flush()
    return primary
