"""POS sale-price versions (spec 4.2 product_sale_prices) + cost history.

The POS-active sale price is a versioned row in product_sale_prices with
exactly one is_active row per product (partial unique index). Every write
copies the active price onto products.selling_price inside the SAME
transaction, so POS and the Stock list never diverge. Cost history is
read-only and derived from confirmed Stock In lots.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.stock.models import (
    Product,
    ProductSalePrice,
    ProductSalePriceUom,
    StockTransaction,
    StockTransactionItem,
)
from app.shared.audit.service import record_audit
from app.shared.pagination.params import parse_date_range

TWO = Decimal("0.01")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _batch_scope(batch_no: str | None) -> str | None:
    """Normalize the batch scope: blank/whitespace = general pricing (None)."""
    text_value = str(batch_no or "").strip()
    return text_value or None


def _active_flag(row: dict) -> bool:
    """POS-active flag of a UOM price row: an explicit False disables it, an
    omitted/None value keeps the row active (default true)."""
    value = row.get("is_active")
    if value is None:
        value = row.get("isActive")
    return True if value is None else bool(value)


async def _deactivate_matching_scope(session: AsyncSession, *, product_id, batch_no: str | None) -> None:
    """Retire the currently ACTIVE version of the SAME (product, batch scope)
    — other scopes (e.g. a batch-specific price) stay active."""
    scope = _batch_scope(batch_no)
    scope_expr = func.coalesce(ProductSalePrice.batch_no, "")
    await session.execute(
        ProductSalePrice.__table__.update()
        .where(
            ProductSalePrice.product_id == product_id,
            ProductSalePrice.is_active.is_(True),
            scope_expr == (scope or ""),
        )
        .values(is_active=False)
    )


async def _validate_uom_prices(
    session: AsyncSession,
    rows: list[dict],
    *,
    base_uom_id,
) -> list[dict]:
    """Validate the version's UOM price rows: known ACTIVE UOMs, positive
    factors/prices, unique UOM per version; snapshots missing symbols.
    Marks the default-sale row (the flagged row, else the base-UOM row,
    else the first row)."""
    from app.modules.uoms.models import UOM

    if not rows:
        raise ValidationError(
            "A price version needs at least one UOM price",
            field_errors={"uom_prices": "At least one UOM price is required"},
        )
    seen: set[str] = set()
    cleaned: list[dict] = []
    default_index: int | None = None
    for index, row in enumerate(rows):
        uom_key = str(row.get("uom_id") or "")
        if not uom_key:
            raise ValidationError(
                "Each UOM price needs a UOM",
                field_errors={"uom_prices": "uom_id is required"},
            )
        if uom_key in seen:
            raise ValidationError(
                "Duplicate UOM in the price version",
                field_errors={"uom_prices": "Duplicate UOM"},
            )
        seen.add(uom_key)
        try:
            factor = Decimal(str(row.get("factor_to_base", 1)))
            price = Decimal(str(row.get("sale_price"))).quantize(TWO, rounding=ROUND_HALF_UP)
        except Exception as exc:
            raise ValidationError(
                "Invalid UOM price row",
                field_errors={"uom_prices": "Invalid factor or price"},
            ) from exc
        if factor <= 0:
            raise ValidationError(
                "Conversion qty must be greater than zero",
                field_errors={"uom_prices": "factor_to_base must be > 0"},
            )
        if price <= 0:
            raise ValidationError(
                "Sale price must be greater than zero",
                field_errors={"uom_prices": "sale_price must be > 0"},
            )
        uom = await session.get(UOM, uuid.UUID(uom_key))
        if uom is None:
            raise NotFoundError("UOM not found")
        if uom.status != "ACTIVE":
            raise ValidationError(
                "Inactive UOMs cannot be used in price versions",
                field_errors={"uom_prices": "UOM is inactive"},
            )
        if bool(row.get("is_default_sale")) and default_index is None:
            default_index = index
        cleaned.append(
            {
                "uom_id": uuid.UUID(uom_key),
                "uom_symbol": str(row.get("uom_symbol") or "").strip() or uom.symbol,
                "factor_to_base": factor,
                "sale_price": price,
                "is_default_sale": False,
                "is_active": _active_flag(row),
            }
        )
    if default_index is None:
        default_index = next(
            (i for i, row in enumerate(cleaned) if str(row["uom_id"]) == str(base_uom_id)),
            0,
        )
    cleaned[default_index]["is_default_sale"] = True
    return cleaned


async def _lock_product(session: AsyncSession, product_id) -> Product:
    """Serialize concurrent price writes per product so the exclusive-active
    invariant holds even under parallel requests."""
    result = await session.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("Product not found")
    return product


async def seed_initial_sale_price(session: AsyncSession, product: Product, *, actor_id=None) -> ProductSalePrice:
    """Version 1, POS-active, mirroring the created product's selling price.
    Ships with a single base-UOM price row (factor 1)."""
    row = ProductSalePrice(
        product_id=product.id,
        sale_price=Decimal(product.selling_price).quantize(TWO, rounding=ROUND_HALF_UP),
        effective_date=_today(),
        is_active=True,
        version=1,
        created_by=actor_id,
    )
    from app.modules.uoms.models import UOM

    base_uom = await session.get(UOM, product.uom_id)
    row.uom_prices.append(
        ProductSalePriceUom(
            uom_id=product.uom_id,
            uom_symbol=base_uom.symbol if base_uom else None,
            factor_to_base=Decimal("1"),
            sale_price=row.sale_price,
            is_default_sale=True,
            is_active=True,
        )
    )
    session.add(row)
    await session.flush()
    return row


def _serialize_uom_price(row: ProductSalePriceUom) -> dict:
    return {
        "id": row.id,
        "uom_id": row.uom_id,
        "uomId": row.uom_id,
        "uom_symbol": row.uom_symbol,
        "uomSymbol": row.uom_symbol,
        "factor_to_base": row.factor_to_base,
        "factorToBase": row.factor_to_base,
        "sale_price": row.sale_price,
        "salePrice": row.sale_price,
        "is_default_sale": row.is_default_sale,
        "isDefaultSale": row.is_default_sale,
        "is_active": row.is_active,
        "isActive": row.is_active,
    }


def _serialize_version(
    row: ProductSalePrice,
    product_name: str | None = None,
    *,
    selling_price=None,
) -> dict:
    """Version payload: scope/dates + the UOM price rows inside it."""
    data = {
        "id": row.id,
        "product_id": row.product_id,
        "productId": row.product_id,
        "sale_price": row.sale_price,
        "salePrice": row.sale_price,
        "effective_date": row.effective_date,
        "effectiveDate": row.effective_date,
        "date": row.effective_date,
        "is_active": row.is_active,
        "isActive": row.is_active,
        "version": row.version,
        "batch_no": row.batch_no,
        "batchNo": row.batch_no,
        "purchase_date": row.purchase_date,
        "purchaseDate": row.purchase_date,
        "expiry_date": row.expiry_date,
        "expiryDate": row.expiry_date,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "uom_prices": [_serialize_uom_price(child) for child in row.uom_prices],
        "uomPrices": [_serialize_uom_price(child) for child in row.uom_prices],
    }
    if product_name is not None:
        data["product"] = product_name
    if selling_price is not None:
        data["selling_price"] = selling_price
    return data


async def list_sale_prices(
    session: AsyncSession,
    *,
    product_id: uuid.UUID | None,
    q: str | None,
    start: str | None,
    end: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict], int]:
    conditions = []
    if product_id is not None:
        conditions.append(ProductSalePrice.product_id == product_id)
    start_at, end_at = parse_date_range(start, end)
    if start_at is not None:
        conditions.append(ProductSalePrice.effective_date >= start_at.date())
    if end_at is not None:
        conditions.append(ProductSalePrice.effective_date <= end_at.date())
    if q and q.strip():
        conditions.append(Product.name.ilike(f"%{q.strip()}%"))

    count_stmt = (
        select(func.count())
        .select_from(ProductSalePrice)
        .join(Product, Product.id == ProductSalePrice.product_id)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    rows = (
        await session.execute(
            select(ProductSalePrice, Product.name)
            .join(Product, Product.id == ProductSalePrice.product_id)
            .options(selectinload(ProductSalePrice.uom_prices))
            .where(*conditions)
            .order_by(ProductSalePrice.effective_date.desc(), ProductSalePrice.version.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    data = [_serialize_version(price, name) for price, name in rows]
    return data, int(total)


async def add_sale_price(
    session: AsyncSession,
    *,
    product_id,
    sale_price,
    effective_date: date | None,
    actor: User,
    batch_no: str | None = None,
    purchase_date: date | None = None,
    expiry_date: date | None = None,
    uom_prices: list[dict] | None = None,
) -> dict:
    """Add version MAX(version)+1 (per product) with its batch scope and
    per-UOM price rows, and make it the ONLY active version of that scope."""
    amount = Decimal(sale_price).quantize(TWO, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Sale price must be greater than zero", field_errors={"sale_price": "Must be > 0"})
    scope = _batch_scope(batch_no)

    product = await _lock_product(session, product_id)

    # UOM price rows inside the version; fall back to a single base-UOM row
    # at `sale_price` when the caller sends none (legacy payload).
    uom_rows = await _validate_uom_prices(
        session,
        [dict(row) for row in (uom_prices or [])],
        base_uom_id=product.uom_id,
    ) if uom_prices else [
        {
            "uom_id": product.uom_id,
            "uom_symbol": product.uom_ref.symbol if product.uom_ref else None,
            "factor_to_base": Decimal("1"),
            "sale_price": amount,
            "is_default_sale": True,
            "is_active": True,
        }
    ]
    default_price = next(
        (row["sale_price"] for row in uom_rows if row["is_default_sale"]),
        amount,
    )

    max_version = (
        await session.execute(
            select(func.coalesce(func.max(ProductSalePrice.version), 0)).where(
                ProductSalePrice.product_id == product.id
            )
        )
    ).scalar_one()
    version = int(max_version) + 1

    # Retire the current active version of the SAME batch scope, then
    # activate the new one (other scopes stay active).
    await _deactivate_matching_scope(session, product_id=product.id, batch_no=scope)
    row = ProductSalePrice(
        product_id=product.id,
        sale_price=default_price,
        effective_date=effective_date or _today(),
        is_active=True,
        version=version,
        batch_no=scope,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        created_by=actor.id,
    )
    for uom_row in uom_rows:
        row.uom_prices.append(ProductSalePriceUom(**uom_row))
    session.add(row)

    # Only the GENERAL (product-wide) version mirrors products.selling_price.
    # A batch-scoped version must not overwrite it: POS resolves the general
    # active version (no batch at cart time), so mirroring a batch price would
    # desync the Stock list from the price POS actually charges.
    if scope is None:
        product.selling_price = default_price
    await session.flush()

    await record_audit(
        session,
        action="sale_price_added",
        module="stock",
        user_id=actor.id,
        entity_type="product_sale_price",
        entity_id=row.id,
        new_values={
            "product_id": str(product.id),
            "version": version,
            "sale_price": str(default_price),
            "batch_no": scope,
            "uom_prices": [str(r["sale_price"]) for r in uom_rows],
        },
    )
    await session.commit()
    return _serialize_version(row, selling_price=product.selling_price)


def uom_price_rows_from_conversions(
    conversions,
    *,
    base_uom_id,
    base_sale_price=None,
) -> list[dict]:
    """Map a product's normalized `uom_conversions` rows to the per-UOM price
    rows of a sale-price version, preserving each row's POS-active flag.

    `base_sale_price` overrides the base-UOM row price (a pure selling-price
    change); a missing base row is synthesized so the version stays sellable
    in the product base UOM. Rows without a positive price are dropped.
    """
    rows: list[dict] = []
    base_key = str(base_uom_id)
    has_base = False
    for row in conversions or []:
        uom_key = str(row.get("uom_id") or row.get("uomId") or "").strip()
        if not uom_key:
            continue
        price_raw = row.get("sale_price", row.get("salePrice"))
        if uom_key == base_key:
            has_base = True
            if base_sale_price is not None:
                price_raw = base_sale_price
        try:
            factor = Decimal(str(row.get("factor_to_base", row.get("factorToBase", 1))))
            price = Decimal(str(price_raw)).quantize(TWO, rounding=ROUND_HALF_UP)
        except Exception:
            continue
        if price <= 0:
            continue
        rows.append(
            {
                "uom_id": uuid.UUID(uom_key),
                "uom_symbol": row.get("uom_symbol") or row.get("uomSymbol"),
                "factor_to_base": factor,
                "sale_price": price,
                "is_default_sale": bool(row.get("is_default_sale", row.get("isDefaultSale", False))),
                "is_active": _active_flag(row),
            }
        )
    if not has_base and base_sale_price is not None and Decimal(str(base_sale_price)) > 0:
        rows.insert(
            0,
            {
                "uom_id": uuid.UUID(base_key),
                "uom_symbol": None,
                "factor_to_base": Decimal("1"),
                "sale_price": Decimal(str(base_sale_price)).quantize(TWO, rounding=ROUND_HALF_UP),
                "is_default_sale": not any(row["is_default_sale"] for row in rows),
                "is_active": True,
            },
        )
    return rows


async def general_version_differs(session: AsyncSession, product_id, rows: list[dict]) -> bool:
    """True when the incoming UOM rows differ (price, factor, default-sale or
    POS-active flag) from the product's active GENERAL price version — so the
    product form only writes a new version when the Pricing table changed."""
    result = await session.execute(
        select(ProductSalePrice)
        .where(
            ProductSalePrice.product_id == product_id,
            ProductSalePrice.is_active.is_(True),
            ProductSalePrice.batch_no.is_(None),
        )
        .options(selectinload(ProductSalePrice.uom_prices))
        .limit(1)
    )
    active = result.scalar_one_or_none()
    if active is None:
        return True
    current = {
        str(child.uom_id): (
            Decimal(child.sale_price),
            Decimal(child.factor_to_base),
            bool(child.is_default_sale),
            bool(child.is_active),
        )
        for child in active.uom_prices
    }
    incoming = {
        str(row["uom_id"]): (
            Decimal(row["sale_price"]),
            Decimal(row["factor_to_base"]),
            bool(row["is_default_sale"]),
            bool(row["is_active"]),
        )
        for row in rows
    }
    return current != incoming


async def activate_sale_price(session: AsyncSession, *, price_id, actor: User) -> dict:
    """Make exactly this version the active one of its (product, batch
    scope) — rejects foreign rows; other scopes keep their active version."""
    # Lock the product FIRST so concurrent activations serialize; the row is
    # re-read after the lock because another transaction may have committed a
    # newer is_active state while this one waited.
    result = await session.execute(select(ProductSalePrice.product_id).where(ProductSalePrice.id == price_id))
    product_id = result.scalar_one_or_none()
    if product_id is None:
        raise NotFoundError("Sale price version not found")

    product = await _lock_product(session, product_id)

    result = await session.execute(
        select(ProductSalePrice)
        .where(ProductSalePrice.id == price_id)
        .options(selectinload(ProductSalePrice.uom_prices))
    )
    row = result.scalar_one()

    await _deactivate_matching_scope(session, product_id=row.product_id, batch_no=row.batch_no)
    # Explicit UPDATE: the ORM attribute may already read True from a stale
    # snapshot, which would skip the flush and leave zero active rows.
    await session.execute(
        ProductSalePrice.__table__.update().where(ProductSalePrice.id == row.id).values(is_active=True)
    )
    row.is_active = True
    default_price = row.default_uom_price()
    # General versions mirror products.selling_price; batch-scoped versions do
    # not (POS always resolves the general version — see add_sale_price).
    if _batch_scope(row.batch_no) is None:
        product.selling_price = Decimal(default_price).quantize(TWO, rounding=ROUND_HALF_UP)
    await session.flush()

    await record_audit(
        session,
        action="sale_price_activated",
        module="stock",
        user_id=actor.id,
        entity_type="product_sale_price",
        entity_id=row.id,
        new_values={
            "product_id": str(row.product_id),
            "version": row.version,
            "sale_price": str(default_price),
        },
    )
    await session.commit()
    return _serialize_version(row, selling_price=product.selling_price)


async def patch_sale_price(
    session: AsyncSession, *, price_id, payload, actor: User
) -> dict:
    """PATCH with isActive=true runs the activate transaction; isActive=false
    deactivates that row (the caller then activates another version)."""
    result = await session.execute(
        select(ProductSalePrice)
        .where(ProductSalePrice.id == price_id)
        .options(selectinload(ProductSalePrice.uom_prices))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("Sale price version not found")

    if payload.is_active is True:
        return await activate_sale_price(session, price_id=price_id, actor=actor)

    product = await _lock_product(session, row.product_id)
    row.is_active = bool(payload.is_active) if payload.is_active is not None else row.is_active
    await session.flush()
    await record_audit(
        session,
        action="sale_price_updated",
        module="stock",
        user_id=actor.id,
        entity_type="product_sale_price",
        entity_id=row.id,
        new_values={"product_id": str(row.product_id), "is_active": row.is_active},
    )
    await session.commit()
    return _serialize_version(row, selling_price=product.selling_price)


async def active_version_uom_prices(
    session: AsyncSession,
    product_id,
    *,
    batch_no: str | None = None,
) -> dict[str, Decimal]:
    """Per-UOM sale prices of the ACTIVE version, keyed by UOM id.

    Batch-first resolution: when a batch is given, the batch-specific active
    version wins; without one (or when no batch version exists) the general
    active version (batch_no NULL) is used. POS picks the correct price by
    the cart line's chosen UOM from this map.
    """
    scope = _batch_scope(batch_no)
    base_conditions = [
        ProductSalePrice.product_id == product_id,
        ProductSalePrice.is_active.is_(True),
    ]
    conditions = [*base_conditions, ProductSalePrice.batch_no == scope if scope else ProductSalePrice.batch_no.is_(None)]
    row = (
        await session.execute(select(ProductSalePrice).where(*conditions).limit(1))
    ).scalar_one_or_none()
    if row is None and scope:
        # Batch-specific version missing → fall back to the general one.
        row = (
            await session.execute(
                select(ProductSalePrice)
                .where(*base_conditions, ProductSalePrice.batch_no.is_(None))
                .limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        return {}
    children = await session.execute(
        select(ProductSalePriceUom).where(
            ProductSalePriceUom.price_version_id == row.id,
            ProductSalePriceUom.is_active.is_(True),
        )
    )
    return {str(child.uom_id): Decimal(child.sale_price) for child in children.scalars().all()}


# --------------------------------------------------- batch-aware POS pricing


async def batch_pos_prices(session: AsyncSession, products) -> dict:
    """Bulk FEFO-aware POS price + sellable stock for product rows.

    One query for the eligible lots and one for the active price versions of
    every product (never a per-product lookup, spec: no POS N+1). For each
    product returns::

        {
            "sellable_stock": Decimal,   # sum of active, unexpired lots
            "next_batch_no": str | None, # FEFO-first lot (the one POS consumes)
            "prices": {uom_id: Decimal}, # that lot's active UOM prices
            "base_price": Decimal | None,# prices[product.uom_id]
            "price_configured": bool,    # a price exists for the base UOM
        }

    The lot's price version wins; when the lot has no scoped version the
    product's general active version applies (a batch price, once configured,
    fully replaces the general price for that lot)."""
    from app.modules.stock.batch_service import business_today
    from app.modules.stock.models import BatchStockBalance

    ids = [p.id for p in products]
    if not ids:
        return {}
    today = await business_today(session)

    lot_rows = await session.execute(
        select(BatchStockBalance)
        .where(
            BatchStockBalance.product_id.in_(ids),
            BatchStockBalance.remaining_quantity > 0,
            BatchStockBalance.is_active.is_(True),
            (BatchStockBalance.expiry_date.is_(None))
            | (BatchStockBalance.expiry_date >= today),
        )
        .order_by(
            BatchStockBalance.expiry_date.is_(None),
            BatchStockBalance.expiry_date.asc(),
            BatchStockBalance.created_at.asc(),
            BatchStockBalance.id.asc(),
        )
    )
    fefo: dict = {}
    sellable: dict = {}
    lots_by_product: dict = {}
    for batch in lot_rows.scalars().all():
        sellable[batch.product_id] = (
            sellable.get(batch.product_id, Decimal("0")) + Decimal(batch.remaining_quantity)
        )
        fefo.setdefault(batch.product_id, batch)
        lots_by_product.setdefault(batch.product_id, []).append(batch)

    version_rows = await session.execute(
        select(ProductSalePrice)
        .where(
            ProductSalePrice.product_id.in_(ids),
            ProductSalePrice.is_active.is_(True),
        )
        .options(selectinload(ProductSalePrice.uom_prices))
    )
    scopes_by_product: dict = {}
    for version in version_rows.scalars().all():
        scopes_by_product.setdefault(version.product_id, {})[str(version.batch_no or "")] = version

    def _base_uom_price(version) -> Decimal | None:
        if version is None:
            return None
        for child in version.uom_prices:
            if child.is_active and child.is_default_sale and Decimal(child.sale_price) > 0:
                return Decimal(child.sale_price)
        return None

    result: dict = {}
    for product in products:
        scopes = scopes_by_product.get(product.id, {})
        batch = fefo.get(product.id)
        version = None
        if batch is not None:
            version = scopes.get(str(batch.batch_no or ""))
        if version is None:
            version = scopes.get("")
        prices: dict[str, Decimal] = {}
        if version is not None:
            prices = {
                str(child.uom_id): Decimal(child.sale_price)
                for child in version.uom_prices
                if child.is_active
            }
        base_price = prices.get(str(product.uom_id))
        if base_price is not None and base_price <= 0:
            base_price = None
        general_base = _base_uom_price(scopes.get(""))
        # FEFO-ordered lots with this product's base-UOM price per lot — lets
        # the POS cart allocate a quantity across lots and show the breakdown.
        lots: list[dict] = []
        for lot in lots_by_product.get(product.id, []):
            lot_version = scopes.get(str(lot.batch_no or ""))
            lot_base = _base_uom_price(lot_version)
            if lot_base is None:
                lot_base = general_base
            lots.append(
                {
                    "batch_no": lot.batch_no,
                    "remaining_quantity": Decimal(lot.remaining_quantity),
                    "expiry_date": lot.expiry_date,
                    "unit_price": lot_base,
                }
            )
        result[product.id] = {
            "sellable_stock": sellable.get(product.id, Decimal("0")),
            "next_batch_no": batch.batch_no if batch is not None else None,
            "prices": prices,
            "base_price": base_price,
            "price_configured": base_price is not None,
            "batches": lots,
        }
    return result


# ------------------------------------------------------------- cost history


async def product_cost_history(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    q: str | None,
    start: str | None,
    end: str | None,
    page: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Read-only cost-price versions derived from confirmed Stock In lots.

    Lots are sorted oldest → newest to assign version 1, 2, 3… and returned
    newest first. There is deliberately no write path — costs are created
    only by Stock In.
    """
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("Product not found")

    conditions = [
        StockTransactionItem.product_id == product_id,
        StockTransaction.transaction_type == "STOCK_IN",
        StockTransaction.status == "CONFIRMED",
    ]
    start_at, end_at = parse_date_range(start, end)
    if start_at is not None:
        conditions.append(StockTransaction.transaction_date >= start_at)
    if end_at is not None:
        conditions.append(StockTransaction.transaction_date <= end_at)
    if q and q.strip():
        conditions.append(StockTransaction.document_no.ilike(f"%{q.strip()}%"))

    rows = (
        await session.execute(
            select(StockTransactionItem, StockTransaction.transaction_date, StockTransaction.document_no)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .where(*conditions)
            .order_by(StockTransaction.transaction_date.asc(), StockTransactionItem.created_at.asc())
        )
    ).all()

    lots = []
    for version, (item, transaction_date, document_no) in enumerate(rows, start=1):
        qty = Decimal(item.quantity)
        unit_cost = Decimal(item.unit_cost)
        lots.append(
            {
                "id": item.id,
                "date": transaction_date,
                "product_id": product_id,
                "productId": product_id,
                "product_name": product.name,
                "unit_cost": unit_cost,
                "unitCost": unit_cost,
                "qty": qty,
                "amount": (qty * unit_cost).quantize(TWO, rounding=ROUND_HALF_UP),
                "version": version,
                "document_no": document_no,
                "documentNo": document_no,
            }
        )
    lots.reverse()

    total = len(lots)
    offset = (page - 1) * limit
    return lots[offset : offset + limit], total


# ------------------------------------------------------- uom conversions


def normalize_uom_conversions(
    rows,
    *,
    base_uom_id,
    base_sale_price=None,
) -> list[dict]:
    """Validate a products.uom_conversions payload (spec 4.2 / spec §2.1.3).

    Pricing rows: unique Original UOM per product (the base UOM row is
    allowed and pinned to factor 1), factor_to_base > 0, sale_price > 0 on
    every row (each Pricing row is sellable on POS), Convert UOM defaults to
    the product base UOM, and exactly one row has is_default_sale = true
    (the base row when nothing is marked). A missing base row is synthesized
    from `base_sale_price` so the product always keeps one sellable row.
    Legacy `use_on_pos` keys are accepted and dropped (always-true).
    """
    rows = rows if isinstance(rows, list) else []
    base_key = str(base_uom_id)
    cleaned: list[dict] = []
    seen: set[str] = set()
    default_index: int | None = None
    for row in rows or []:
        uom_id = str(row.get("uom_id") or row.get("uomId") or "").strip()
        if not uom_id:
            raise ValidationError(
                "Each pricing row needs a UOM",
                field_errors={"uom_conversions": "uom_id is required"},
            )
        if uom_id in seen:
            raise ValidationError(
                "Duplicate Original UOM — each UOM may appear once per product",
                field_errors={"uom_conversions": "Duplicate UOM"},
            )
        seen.add(uom_id)
        is_base = uom_id == base_key
        try:
            factor = Decimal(str(row.get("factor_to_base", row.get("factorToBase", 1))))
        except Exception as exc:
            raise ValidationError("Invalid factor_to_base", field_errors={"uom_conversions": "Invalid factor"}) from exc
        if is_base:
            # A base=base row is always exactly 1.
            factor = Decimal("1")
        elif factor <= 0:
            raise ValidationError(
                "Conversion qty must be greater than zero",
                field_errors={"uom_conversions": "factor_to_base must be > 0"},
            )
        sale_price = row.get("sale_price", row.get("salePrice"))
        if sale_price is None or Decimal(str(sale_price)) <= 0:
            raise ValidationError(
                "Sale price must be greater than zero for every Pricing row",
                field_errors={"uom_conversions": "Pricing row requires sale_price"},
            )
        convert_uom_id = str(row.get("convert_uom_id") or row.get("convertUomId") or "").strip() or base_key
        if not is_base and convert_uom_id == uom_id:
            raise ValidationError(
                "A pack row must convert into a different UOM",
                field_errors={"uom_conversions": "Convert UOM equals Original UOM"},
            )
        cost_price = row.get("cost_price", row.get("costPrice"))
        cleaned.append(
            {
                "uom_id": uom_id,
                "uom_symbol": str(row.get("uom_symbol") or row.get("uomSymbol") or ""),
                "convert_uom_id": convert_uom_id,
                "convert_uom_symbol": str(row.get("convert_uom_symbol") or row.get("convertUomSymbol") or ""),
                "factor_to_base": str(factor),
                "cost_price": str(Decimal(str(cost_price))) if cost_price is not None else None,
                "sale_price": str(Decimal(str(sale_price))),
                "is_default_sale": False,
                # POS-active flag per UOM (default: active).
                "is_active": _active_flag(row),
            }
        )
        if bool(row.get("is_default_sale", row.get("isDefaultSale", False))) and default_index is None:
            default_index = len(cleaned) - 1
    # Exactly one default-sale row: the marked row, else the base row,
    # else the first row.
    has_default = False
    if cleaned:
        if default_index is None:
            default_index = next(
                (i for i, row in enumerate(cleaned) if row["uom_id"] == base_key),
                0,
            )
        cleaned[default_index]["is_default_sale"] = True
        has_default = True
    if base_key not in seen and base_sale_price is not None:
        # Keep at least one sellable row (spec §2.1.3): synthesize the base row.
        if Decimal(str(base_sale_price)) <= 0:
            raise ValidationError(
                "Sale price must be greater than zero for every Pricing row",
                field_errors={"uom_conversions": "Pricing row requires sale_price"},
            )
        # The base row leads the Pricing table (front end ordering).
        cleaned.insert(0,
            {
                "uom_id": base_key,
                "uom_symbol": "",
                "convert_uom_id": base_key,
                "convert_uom_symbol": "",
                "factor_to_base": "1",
                "cost_price": None,
                "sale_price": str(Decimal(str(base_sale_price))),
                "is_default_sale": not has_default,
                "is_active": True,
            }
        )
    return cleaned


async def validate_conversion_uoms(session: AsyncSession, rows: list[dict]) -> None:
    """Every Original/Convert UOM must reference an existing, ACTIVE UOM;
    fills missing symbol snapshots from the UOM records."""
    from app.modules.uoms.models import UOM

    checked: dict[str, UOM] = {}
    for row in rows:
        for key in ("uom_id", "convert_uom_id"):
            uom_key = str(row.get(key) or "")
            if not uom_key:
                continue
            uom = checked.get(uom_key)
            if uom is None:
                uom = await session.get(UOM, uuid.UUID(uom_key))
                if uom is None:
                    raise NotFoundError("UOM not found")
                if uom.status != "ACTIVE":
                    raise ValidationError(
                        "Inactive UOMs cannot be used in pricing rows",
                        field_errors={"uom_conversions": "UOM is inactive"},
                    )
                checked[uom_key] = uom
            if key == "uom_id" and not row.get("uom_symbol"):
                row["uom_symbol"] = uom.symbol
            if key == "convert_uom_id" and not row.get("convert_uom_symbol"):
                row["convert_uom_symbol"] = uom.symbol
