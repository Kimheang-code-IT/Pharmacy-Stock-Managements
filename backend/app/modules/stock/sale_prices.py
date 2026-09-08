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

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.stock.models import (
    Product,
    ProductSalePrice,
    StockTransaction,
    StockTransactionItem,
)
from app.shared.audit.service import record_audit
from app.shared.pagination.params import parse_date_range

TWO = Decimal("0.01")


def _today() -> date:
    return datetime.now(timezone.utc).date()


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
    """Version 1, POS-active, mirroring the created product's selling price."""
    row = ProductSalePrice(
        product_id=product.id,
        sale_price=Decimal(product.selling_price).quantize(TWO, rounding=ROUND_HALF_UP),
        effective_date=_today(),
        is_active=True,
        version=1,
        created_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return row


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

    rows = await session.execute(
        select(ProductSalePrice, Product.name)
        .join(Product, Product.id == ProductSalePrice.product_id)
        .where(*conditions)
        .order_by(ProductSalePrice.effective_date.desc(), ProductSalePrice.version.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    data = [
        {
            "id": price.id,
            "product_id": price.product_id,
            "productId": price.product_id,
            "product": name,
            "sale_price": price.sale_price,
            "salePrice": price.sale_price,
            "effective_date": price.effective_date,
            "effectiveDate": price.effective_date,
            "date": price.effective_date,
            "is_active": price.is_active,
            "isActive": price.is_active,
            "version": price.version,
            "created_by": price.created_by,
            "created_at": price.created_at,
        }
        for price, name in rows.all()
    ]
    return data, int(total)


async def add_sale_price(
    session: AsyncSession,
    *,
    product_id,
    sale_price,
    effective_date: date | None,
    actor: User,
) -> dict:
    """Add version MAX(version)+1 and make it the ONLY POS-active row."""
    amount = Decimal(sale_price).quantize(TWO, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Sale price must be greater than zero", field_errors={"sale_price": "Must be > 0"})

    product = await _lock_product(session, product_id)

    max_version = (
        await session.execute(
            select(func.coalesce(func.max(ProductSalePrice.version), 0)).where(
                ProductSalePrice.product_id == product.id
            )
        )
    ).scalar_one()
    version = int(max_version) + 1

    # Retire the current active row, then activate the new version.
    await session.execute(
        ProductSalePrice.__table__.update()
        .where(ProductSalePrice.product_id == product.id, ProductSalePrice.is_active.is_(True))
        .values(is_active=False)
    )
    row = ProductSalePrice(
        product_id=product.id,
        sale_price=amount,
        effective_date=effective_date or _today(),
        is_active=True,
        version=version,
        created_by=actor.id,
    )
    session.add(row)

    product.selling_price = amount
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
            "sale_price": str(amount),
        },
    )
    await session.commit()
    return {
        "id": row.id,
        "product_id": row.product_id,
        "productId": row.product_id,
        "sale_price": row.sale_price,
        "salePrice": row.sale_price,
        "effective_date": row.effective_date,
        "effectiveDate": row.effective_date,
        "is_active": row.is_active,
        "isActive": row.is_active,
        "version": row.version,
        "selling_price": product.selling_price,
    }


async def activate_sale_price(session: AsyncSession, *, price_id, actor: User) -> dict:
    """Make exactly this version the POS-active one (rejects foreign rows)."""
    # Lock the product FIRST so concurrent activations serialize; the row is
    # re-read after the lock because another transaction may have committed a
    # newer is_active state while this one waited.
    result = await session.execute(select(ProductSalePrice.product_id).where(ProductSalePrice.id == price_id))
    product_id = result.scalar_one_or_none()
    if product_id is None:
        raise NotFoundError("Sale price version not found")

    product = await _lock_product(session, product_id)

    result = await session.execute(select(ProductSalePrice).where(ProductSalePrice.id == price_id))
    row = result.scalar_one()

    await session.execute(
        ProductSalePrice.__table__.update()
        .where(ProductSalePrice.product_id == row.product_id, ProductSalePrice.is_active.is_(True))
        .values(is_active=False)
    )
    # Explicit UPDATE: the ORM attribute may already read True from a stale
    # snapshot, which would skip the flush and leave zero active rows.
    await session.execute(
        ProductSalePrice.__table__.update().where(ProductSalePrice.id == row.id).values(is_active=True)
    )
    row.is_active = True
    product.selling_price = Decimal(row.sale_price).quantize(TWO, rounding=ROUND_HALF_UP)
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
            "sale_price": str(row.sale_price),
        },
    )
    await session.commit()
    return {
        "id": row.id,
        "product_id": row.product_id,
        "productId": row.product_id,
        "sale_price": row.sale_price,
        "salePrice": row.sale_price,
        "effective_date": row.effective_date,
        "effectiveDate": row.effective_date,
        "is_active": row.is_active,
        "isActive": row.is_active,
        "version": row.version,
        "selling_price": product.selling_price,
    }


async def patch_sale_price(
    session: AsyncSession, *, price_id, payload, actor: User
) -> dict:
    """PATCH with isActive=true runs the activate transaction; isActive=false
    deactivates that row (the caller then activates another version)."""
    result = await session.execute(select(ProductSalePrice).where(ProductSalePrice.id == price_id))
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
    return {
        "id": row.id,
        "product_id": row.product_id,
        "productId": row.product_id,
        "sale_price": row.sale_price,
        "salePrice": row.sale_price,
        "effective_date": row.effective_date,
        "effectiveDate": row.effective_date,
        "is_active": row.is_active,
        "isActive": row.is_active,
        "version": row.version,
        "selling_price": product.selling_price,
    }


async def product_active_price(session: AsyncSession, product_id) -> Decimal:
    """The POS-active sale price for a product (selling_price mirror)."""
    result = await session.execute(
        select(ProductSalePrice.sale_price)
        .where(ProductSalePrice.product_id == product_id, ProductSalePrice.is_active.is_(True))
        .limit(1)
    )
    value = result.scalar_one_or_none()
    return Decimal(value) if value is not None else Decimal("0.00")


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
