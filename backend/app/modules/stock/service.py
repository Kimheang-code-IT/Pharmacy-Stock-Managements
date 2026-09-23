from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.categories.repository import CategoryRepository
from app.modules.brands.repository import BrandRepository
from app.modules.auth.models import User
from app.shared.lifecycle import assert_inactive_for_delete
from app.modules.stock.models import (
    Product,
    PurchaseReturn,
    PurchaseReturnItem,
    StockBalance,
    StockMovement,
    StockTransaction,
    StockTransactionItem,
)
from app.modules.stock.repository import ProductRepository, product_to_out
from app.modules.stock.schemas import (
    AdjustmentItem,
    DamageItem,
    ExpireItem,
    MovementOut,
    OperationItemOut,
    PurchaseReturnItemOut,
    PurchaseReturnOut,
    StockAdjustmentRequest,
    StockDamageRequest,
    StockExpireRequest,
    StockInItem,
    StockInRequest,
    StockOperationOut,
)
from app.modules.suppliers.models import SupplierDebt
from app.modules.uoms.repository import UOMRepository
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number


class ProductService:
    """Product master data. Stock quantities are never edited here — only the
    canonical stock mutation service may change balances."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProductRepository(session)

    async def _next_barcode(self) -> str:
        """Auto-issue a unique numeric barcode for products created without one.

        Digits only so it scans at POS and prints as a plain number; derived
        from a UUID and collision-checked against existing rows."""
        candidate = self._numeric_barcode()
        while await self.repo.get_by_barcode(candidate):
            candidate = self._numeric_barcode()
        return candidate

    @staticmethod
    def _numeric_barcode() -> str:
        """13-digit numeric code (UUID entropy, zero-padded)."""
        return f"{uuid.uuid4().int % 10**13:013d}"

    async def list(
        self, *, q, category_id, brand_id=None, status, page, limit, sort=None
    ) -> tuple[list[dict], int]:
        products, total = await self.repo.list(
            q=q, category_id=category_id, brand_id=brand_id, status=status, page=page, limit=limit, sort=sort
        )
        grouped = await self.repo.aggregate_movements([p.id for p in products])
        from app.modules.stock import sale_prices as sale_price_service

        pos_map = await sale_price_service.batch_pos_prices(self.session, products)
        return [
            product_to_out(p, grouped=grouped, pos=pos_map.get(p.id)) for p in products
        ], total

    async def get(self, product_id: uuid.UUID) -> dict:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        grouped = await self.repo.aggregate_movements([product.id])
        from app.modules.stock import sale_prices as sale_price_service

        pos_map = await sale_price_service.batch_pos_prices(self.session, [product])
        return product_to_out(product, grouped=grouped, pos=pos_map.get(product.id))

    async def create(self, payload) -> dict:
        # Barcode is the operational identifier: unique, auto-issued when the
        # caller omits it (uuid-derived, collision-checked).
        barcode = payload.barcode or None
        if barcode and await self.repo.get_by_barcode(barcode):
            raise ConflictError("A product with this barcode already exists")
        await self._validate_category(payload.category_id)
        await self._validate_uom(payload.uom_id)
        await self._validate_brand(payload.brand_id)
        await self._validate_supplier(payload.supplier_id)

        data = payload.model_dump()
        conversions = data.pop("uom_conversions", None)
        if conversions:
            from app.modules.stock import sale_prices as sale_price_service

            conversions = sale_price_service.normalize_uom_conversions(
                conversions,
                base_uom_id=payload.uom_id,
                base_sale_price=payload.selling_price,
            )
            await sale_price_service.validate_conversion_uoms(self.session, conversions)
            data["uom_conversions"] = conversions

        product = Product(**data)
        product.barcode = barcode or await self._next_barcode()
        self.session.add(product)
        await self.session.flush()
        await self.repo.ensure_balance(product.id)
        # Seed sale-price version 1 (POS-active) so POS always has a versioned price.
        from app.modules.stock import sale_prices as sale_price_service

        await sale_price_service.seed_initial_sale_price(
            self.session, product, actor_id=None
        )
        await record_audit(
            self.session,
            action="product_created",
            module="stock",
            entity_type="product",
            entity_id=product.id,
            new_values={
                "barcode": product.barcode,
                "name": product.name,
                "status": product.status,
            },
        )
        await self.session.commit()
        await self.session.refresh(product, attribute_names=["category_ref", "brand_ref", "uom_ref", "supplier_ref", "balance"])
        return product_to_out(product)

    async def update(self, product_id: uuid.UUID, payload, *, actor: User) -> dict:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")

        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        old_snapshot = {
            "barcode": product.barcode,
            "name": product.name,
            "status": product.status,
            "category_id": str(product.category_id) if product.category_id else None,
            "uom_id": str(product.uom_id) if product.uom_id else None,
        }
        # image_object_key=None explicitly clears the product image.
        if "image_object_key" in payload.model_fields_set and payload.image_object_key is None:
            changes["image_object_key"] = None
        # supplier_id=None explicitly clears the product's default supplier.
        if "supplier_id" in payload.model_fields_set and payload.supplier_id is None:
            changes["supplier_id"] = None
        # brand=None explicitly clears the free-text brand.
        if "brand" in payload.model_fields_set and payload.brand is None:
            changes["brand"] = None
        if "uom_conversions" in payload.model_fields_set:
            from app.modules.stock import sale_prices as sale_price_service

            conversions = sale_price_service.normalize_uom_conversions(
                payload.uom_conversions or [],
                base_uom_id=changes.get("uom_id", product.uom_id),
                # The base row's sale price follows the POS-active price.
                base_sale_price=changes.get("selling_price", product.selling_price),
            )
            await sale_price_service.validate_conversion_uoms(self.session, conversions)
            changes["uom_conversions"] = conversions
        if "barcode" in changes and changes["barcode"] and changes["barcode"] != product.barcode:
            if await self.repo.get_by_barcode(changes["barcode"]):
                raise ConflictError("A product with this barcode already exists")
        if "category_id" in changes:
            await self._validate_category(changes["category_id"])
        if "uom_id" in changes:
            await self._validate_uom(changes["uom_id"])
        if "brand_id" in changes:
            await self._validate_brand(changes["brand_id"])
        if changes.get("supplier_id") is not None:
            await self._validate_supplier(changes["supplier_id"])

        # A selling-price change becomes "add + activate a new sale-price
        # version" so POS (which reads the active version) never diverges.
        # Same price as the active version is a no-op (the UI re-syncs it).
        new_selling_price = changes.pop("selling_price", None)

        price_changed = {"cost_price"} & set(changes)
        old_prices = (
            {"cost_price": str(product.cost_price)}
            if price_changed
            else None
        )

        for key, value in changes.items():
            setattr(product, key, value)

        # A Pricing save (uom_conversions) or a selling-price change becomes ONE
        # new POS-active general version carrying EVERY UOM row and its per-UOM
        # active flag — so POS always reads a single, consistent active version.
        # An unchanged Pricing table writes nothing (no version churn).
        pricing_touched = "uom_conversions" in payload.model_fields_set
        price_only = (
            new_selling_price is not None
            and Decimal(str(new_selling_price)) != Decimal(str(product.selling_price))
        )
        if pricing_touched or price_only:
            from app.modules.stock import sale_prices as sale_price_service

            general_rows = sale_price_service.uom_price_rows_from_conversions(
                product.uom_conversions or [],
                base_uom_id=product.uom_id,
                base_sale_price=new_selling_price if price_only else None,
            )
            if general_rows and await sale_price_service.general_version_differs(
                self.session, product.id, general_rows
            ):
                default_price = next(
                    (row["sale_price"] for row in general_rows if row["is_default_sale"]),
                    general_rows[0]["sale_price"],
                )
                await sale_price_service.add_sale_price(
                    self.session,
                    product_id=product.id,
                    sale_price=default_price,
                    effective_date=None,
                    actor=actor,
                    uom_prices=general_rows,
                )
        await self.session.flush()

        if price_changed:
            await record_audit(
                self.session,
                action="price_changed",
                module="stock",
                user_id=actor.id,
                entity_type="product",
                entity_id=product.id,
                old_values=old_prices,
                new_values={
                    "cost_price": str(product.cost_price),
                },
            )
        # Audit any other product edit (identity/status/pricing-table changes),
        # not just a cost-price change.
        audited_fields = set(changes)
        if pricing_touched or price_only:
            audited_fields.add("selling_price")
        if audited_fields:
            await record_audit(
                self.session,
                action="product_updated",
                module="stock",
                user_id=actor.id,
                entity_type="product",
                entity_id=product.id,
                old_values=old_snapshot,
                new_values={
                    "changed_fields": sorted(audited_fields),
                    "barcode": product.barcode,
                    "name": product.name,
                    "status": product.status,
                },
            )
        await self.session.commit()
        await self.session.refresh(product, attribute_names=["category_ref", "brand_ref", "uom_ref", "supplier_ref", "balance"])
        return product_to_out(product)

    async def delete(self, product_id: uuid.UUID) -> None:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        assert_inactive_for_delete(product.status, label="product")
        # Hard delete. History rows keep the product name through their
        # snapshots and their product_id is nulled by ON DELETE SET NULL, so
        # purchase/sale/return/delivery history is preserved; stock balances,
        # batches and sale-price versions cascade with the product.
        snapshot = {"barcode": product.barcode, "name": product.name}
        await self.session.delete(product)
        await record_audit(
            self.session,
            action="product_deleted",
            module="stock",
            entity_type="product",
            entity_id=product.id,
            old_values=snapshot,
        )
        await self.session.commit()

    async def _validate_category(self, category_id) -> None:
        if category_id is None:
            return
        if await CategoryRepository(self.session).get(category_id) is None:
            raise NotFoundError("Category not found")

    async def _validate_uom(self, uom_id) -> None:
        """Products require an existing, ACTIVE UOM (spec sections 2.1.3/2.1.5)."""
        if uom_id is None:
            raise ValidationError(
                "A UOM is required for every product",
                field_errors={"uom_id": "UOM is required"},
            )
        uom = await UOMRepository(self.session).get(uom_id)
        if uom is None:
            raise NotFoundError("UOM not found")
        if uom.status != "ACTIVE":
            raise ValidationError(
                "Inactive UOMs cannot be assigned to products",
                field_errors={"uom_id": "UOM is inactive"},
            )

    async def _validate_brand(self, brand_id) -> None:
        """Brand is optional, but when set it must exist and be ACTIVE."""
        if brand_id is None:
            return
        brand = await BrandRepository(self.session).get(brand_id)
        if brand is None:
            raise NotFoundError("Brand not found")
        if brand.status != "ACTIVE":
            raise ValidationError(
                "Inactive brands cannot be assigned to products",
                field_errors={"brand_id": "Brand is inactive"},
            )

    async def _validate_supplier(self, supplier_id) -> None:
        """Default supplier is optional, but when set it must exist."""
        if supplier_id is None:
            return
        from app.modules.suppliers.models import Supplier

        if await self.session.get(Supplier, supplier_id) is None:
            raise NotFoundError("Supplier not found")

# ============================================================================
# Canonical stock mutation service
# ============================================================================
# Every stock change (stock in, adjustment, damage, expiry, POS sale, sale
# return) goes through apply_stock_movement. It locks the balance row, enforces
# availability unless negative stock is allowed, appends an immutable movement,
# and updates the materialized balance in the SAME transaction.

MOVEMENT_TYPES = {
    "STOCK_IN",
    "SALE",
    "SALE_RETURN",
    "PURCHASE_RETURN",
    "ADJUSTMENT_IN",
    "ADJUSTMENT_OUT",
    "DAMAGE",
    "EXPIRE",
}

FOUR = Decimal("0.0001")
TWO = Decimal("0.01")


def _q4(value) -> Decimal:
    return Decimal(value).quantize(FOUR)


def _q2(value) -> Decimal:
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def _usd_unit_cost(amount, currency, exchange_rate) -> Decimal:
    """Convert a document-currency unit cost to the canonical cost currency
    (USD) using the document exchange rate (KHR per 1 USD). Cost ledgers
    (movements, balances, batches, sale-item snapshots) are ALWAYS USD so a
    KHR purchase and a USD sale never contaminate each other (F2)."""
    value = Decimal(amount)
    rate = Decimal(exchange_rate or 1)
    if str(currency or "USD").upper() == "KHR" and rate > 0:
        return (value / rate).quantize(TWO, rounding=ROUND_HALF_UP)
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


async def _lock_balance(session: AsyncSession, product_id) -> StockBalance:
    # populate_existing forces the identity-mapped instance to refresh from the
    # locked row: the caller may have eager-loaded a stale balance beforehand.
    result = await session.execute(
        select(StockBalance)
        .where(StockBalance.product_id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    balance = result.scalar_one_or_none()
    if balance is None:
        balance = StockBalance(product_id=product_id, quantity=Decimal("0"), average_cost=Decimal("0.00"))
        session.add(balance)
        await session.flush()
    return balance


async def allow_negative_stock(session: AsyncSession) -> bool:
    from app.modules.administration import get_setting_value

    return bool(await get_setting_value(session, "pos", "allow_negative_stock", False))


async def fifo_outbound_unit_cost(
    session: AsyncSession, product_id, quantity, *, fallback: Decimal
) -> Decimal:
    """Blended FIFO cost for `quantity` units of a product (product.fifo=True).

    Remaining lots are rebuilt from the immutable stock_movements ledger:
    inbound movements open lots, outbound movements consume them first-in-
    first-out. The returned cost is the quantity-weighted average of the lots
    this outbound consumes. Any shortfall (only possible when negative stock
    is allowed) is priced at the last consumed lot's cost, or `fallback` when
    no lot has ever been recorded. Must run inside the caller's transaction;
    pending movements of the session are flushed by the ledger query so FIFO
    chains correctly across repeated outbounds of the same document.
    """
    quantity = _q4(quantity)
    if quantity <= 0:
        return Decimal(fallback).quantize(TWO, rounding=ROUND_HALF_UP)

    rows = await session.execute(
        select(
            StockMovement.quantity_delta,
            StockMovement.unit_cost,
        )
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
    )
    lots: list[list[Decimal]] = []  # mutable [remaining_qty, unit_cost] heads
    for delta, cost in rows:
        delta = Decimal(delta)
        if delta > 0:
            lots.append([delta, Decimal(cost)])
            continue
        remaining = -delta
        while remaining > 0 and lots:
            head = lots[0]
            if head[0] <= remaining:
                remaining -= head[0]
                lots.pop(0)
            else:
                head[0] -= remaining
                remaining = Decimal("0")

    needed = quantity
    weighted = Decimal("0")
    taken = Decimal("0")
    last_cost = Decimal(fallback)
    for lot in lots:
        if needed <= 0:
            break
        take = min(lot[0], needed)
        weighted += take * lot[1]
        taken += take
        needed -= take
        last_cost = lot[1]
    if needed > 0:
        # Negative-stock shortfall: price the remainder at the last consumed
        # lot's cost (or the fallback when nothing was consumed).
        weighted += needed * last_cost
        taken += needed
    if taken == 0:
        return Decimal(fallback).quantize(TWO, rounding=ROUND_HALF_UP)
    return (weighted / taken).quantize(TWO, rounding=ROUND_HALF_UP)


async def resolve_outbound_unit_cost(
    session: AsyncSession,
    product: Product,
    quantity,
    *,
    fallback: Decimal,
) -> Decimal:
    """Unit cost for an outbound movement: FIFO lots when the product has the
    FIFO option enabled, otherwise the weighted average cost (fallback)."""
    if product.fifo:
        return await fifo_outbound_unit_cost(session, product.id, quantity, fallback=fallback)
    return Decimal(fallback).quantize(TWO, rounding=ROUND_HALF_UP)


async def apply_stock_movement(
    session: AsyncSession,
    *,
    product_id,
    movement_type: str,
    quantity_delta,
    unit_cost,
    reference_type: str,
    reference_id,
    created_by,
    document_no: str | None = None,
    batch_no: str | None = None,
    batch_id=None,
    expiry_date=None,
    note: str | None = None,
    allow_negative: bool | None = None,
    uom_symbol: str | None = None,
) -> StockBalance:
    """Canonical stock mutation. Must run inside the caller's transaction."""
    if movement_type not in MOVEMENT_TYPES:
        raise ValidationError(f"Unknown movement type '{movement_type}'")

    delta = _q4(quantity_delta)
    if delta == 0:
        raise ValidationError("Stock movement quantity cannot be zero")

    balance = await _lock_balance(session, product_id)
    # Snapshot the product name so the movement history survives a hard delete.
    product_name = await session.scalar(select(Product.name).where(Product.id == product_id))

    if delta < 0 and not allow_negative and balance.quantity + delta < 0:
        raise ConflictError(
            f"Insufficient stock: available {balance.quantity}, requested {abs(delta)}"
        )

    if movement_type == "STOCK_IN" and delta > 0 and balance.quantity >= 0:
        total_qty = balance.quantity + delta
        if total_qty > 0:
            weighted = (balance.quantity * balance.average_cost + delta * Decimal(unit_cost)) / total_qty
            balance.average_cost = weighted.quantize(TWO, rounding=ROUND_HALF_UP)
        else:
            balance.average_cost = Decimal(unit_cost).quantize(TWO, rounding=ROUND_HALF_UP)

    movement = StockMovement(
        product_id=product_id,
        product_name=product_name,
        movement_type=movement_type,
        quantity_delta=delta,
        unit_cost=Decimal(unit_cost).quantize(TWO, rounding=ROUND_HALF_UP),
        reference_type=reference_type,
        reference_id=reference_id,
        document_no=document_no,
        batch_no=batch_no,
        batch_id=batch_id,
        expiry_date=expiry_date,
        uom_symbol=uom_symbol,
        note=note,
        created_by=created_by,
    )
    session.add(movement)
    balance.quantity = _q4(balance.quantity + delta)
    await session.flush()
    return balance


class StockOperationService:
    """Transactional stock operations: stock in, adjustment, damage, expiry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.repo = self.products

    async def _get_product(self, product_id):
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        return product

    @staticmethod
    def _resolve_date(value: datetime | None) -> datetime:
        return value or datetime.now(timezone.utc)

    async def _create_transaction(self, *, transaction_type, document_no, payload, actor) -> StockTransaction:
        transaction = StockTransaction(
            document_no=document_no,
            transaction_type=transaction_type,
            transaction_date=self._resolve_date(payload.transaction_date),
            reference_no=payload.reference_no,
            note=payload.note,
            status="CONFIRMED",
            created_by=actor.id,
            confirmed_by=actor.id,
        )
        if getattr(payload, "supplier_id", None):
            transaction.supplier_id = payload.supplier_id
        # Document currency (Stock In only; other payloads lack the fields).
        if hasattr(payload, "currency"):
            transaction.currency = payload.currency
            transaction.exchange_rate = payload.exchange_rate
        # Document-level purchase adjustments (Stock In only; other operation
        # payloads do not carry these fields).
        if hasattr(payload, "discount_amount"):
            transaction.discount_amount = _q2(payload.discount_amount or 0)
            transaction.tax_amount = _q2(payload.tax_amount or 0)
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def stock_in(self, payload, *, actor: User) -> StockOperationOut:
        products: dict = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in request", field_errors={"items": "Duplicate product"})
            products[item.product_id] = await self._get_product(item.product_id)

        supplier_id = payload.supplier_id
        if supplier_id is not None:
            from app.modules.suppliers import Supplier as SupplierModel

            if await self.session.get(SupplierModel, supplier_id) is None:
                raise NotFoundError("Supplier not found")

        negative_ok = await allow_negative_stock(self.session)
        document_no = await allocate_document_number(self.session, "STOCK_IN")
        transaction = await self._create_transaction(
            transaction_type="STOCK_IN", document_no=document_no, payload=payload, actor=actor
        )

        total = Decimal("0.00")
        item_rows: list[StockTransactionItem] = []
        for item in payload.items:
            product = products[item.product_id]

            # Batch-tracked products (spec: batch/lot management): incoming
            # stock MUST be assigned a batch_no, and an expiry date when the
            # product tracks expiry. Unbatched products keep the legacy path.
            if product.track_batch:
                if not (item.batch_no or "").strip():
                    raise ValidationError(
                        "Batch number is required for batch-tracked products",
                        field_errors={"items": "Batch number is required"},
                    )
                if product.expiry_tracking and item.expiry_date is None:
                    raise ValidationError(
                        "Expiry date is required for expiry-tracked products",
                        field_errors={"items": "Expiry date is required"},
                    )

            # ---- line UOM resolution (stock is always mutated in base UOM) ----
            # qty/unit_cost are per the SELECTED Pricing UOM; factor_to_base
            # says how many Convert (base) UOM = 1 Original UOM.
            factor = item.factor_to_base
            if item.uom_id is not None:
                if str(item.uom_id) == str(product.uom_id):
                    factor = Decimal("1")
                else:
                    conversion = next(
                        (
                            row
                            for row in (product.uom_conversions or [])
                            if str(row.get("uom_id")) == str(item.uom_id)
                        ),
                        None,
                    )
                    if conversion is None:
                        raise ValidationError(
                            "The selected UOM is not a Pricing UOM of this product",
                            field_errors={"items": "Invalid UOM"},
                        )
                    row_factor = Decimal(str(conversion.get("factor_to_base", 1)))
                    if factor is not None and Decimal(str(factor)) != row_factor:
                        raise ValidationError(
                            "factor_to_base does not match the product's Pricing row",
                            field_errors={"items": "Invalid factor"},
                        )
                    factor = row_factor
            if factor is None:
                factor = Decimal("1")
            if factor <= 0:
                raise ValidationError(
                    "factor_to_base must be greater than zero",
                    field_errors={"items": "Invalid factor"},
                )
            base_quantity = _q4(Decimal(item.quantity) * factor)
            if base_quantity <= 0:
                raise ValidationError(
                    "Line quantity must be greater than zero",
                    field_errors={"items": "Invalid quantity"},
                )
            # unit_cost is per selected UOM; the transaction line keeps the
            # document-currency cost, while the cost ledger keeps the base-unit
            # cost converted to the canonical USD currency.
            base_unit_cost = (Decimal(item.unit_cost) / factor).quantize(TWO, rounding=ROUND_HALF_UP)
            ledger_unit_cost = _usd_unit_cost(base_unit_cost, transaction.currency, transaction.exchange_rate)
            line_total = (Decimal(item.quantity) * Decimal(item.unit_cost)).quantize(TWO, rounding=ROUND_HALF_UP)
            # Line UOM symbol snapshot: the caller's value or the product's
            # base UOM symbol (display only — quantities stay in base UOM).
            line_uom_symbol = (
                item.uom_symbol
                or (product.uom_ref.symbol if item.uom_id is None and product.uom_ref else None)
            )
            row = StockTransactionItem(
                stock_transaction_id=transaction.id,
                product_id=item.product_id,
                product_ref=product,
                product_name=product.name,
                quantity=base_quantity,
                unit_cost=base_unit_cost,
                batch_no=item.batch_no,
                expiry_date=item.expiry_date,
                uom_symbol=line_uom_symbol,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
            # Batch ledger: the lot carries the traceable purchase (cost per
            # base unit, supplier, purchase document). Unbatched stock still
            # lands in a synthetic lot keyed on "".
            from app.modules.stock import batch_service

            batch_lot = await batch_service.batch_in(
                self.session,
                product_id=item.product_id,
                batch_no=item.batch_no,
                expiry_date=item.expiry_date,
                quantity_base=base_quantity,
                unit_cost_per_base=ledger_unit_cost,
                supplier_id=transaction.supplier_id,
                document_no=document_no,
            )
            # batch_in may have auto-assigned the next batch number (a reused
            # batch_no with a different expiry): record the lot's real number.
            row.batch_no = batch_lot.batch_no or None
            await apply_stock_movement(
                self.session,
                product_id=item.product_id,
                movement_type="STOCK_IN",
                quantity_delta=base_quantity,
                unit_cost=ledger_unit_cost,
                reference_type="stock_transaction",
                reference_id=transaction.id,
                created_by=actor.id,
                document_no=document_no,
                batch_no=batch_lot.batch_no or None,
                # Movement references the lot it stocked into (new or
                # restocked — identity = product + batch_no + expiry).
                batch_id=batch_lot.id if (batch_lot.batch_no or "").strip() else None,
                expiry_date=item.expiry_date,
                allow_negative=negative_ok,
                uom_symbol=line_uom_symbol,
            )
            total += line_total
        subtotal = total.quantize(TWO, rounding=ROUND_HALF_UP)
        discount = _q2(payload.discount_amount or 0)
        tax = _q2(payload.tax_amount or 0)
        if discount > subtotal:
            raise ValidationError(
                "Discount cannot exceed the line subtotal",
                field_errors={"discount_amount": "Discount exceeds subtotal"},
            )
        total = (subtotal - discount + tax).quantize(TWO, rounding=ROUND_HALF_UP)

        paid = min(Decimal(payload.paid_amount), total)
        if paid < Decimal("0"):
            raise ValidationError("Paid amount cannot be negative")
        debt = None
        if paid < total:
            if supplier_id is None:
                raise ValidationError(
                    "Full payment is required when no supplier is selected",
                    field_errors={"paid_amount": "Full payment required"},
                )
            from app.modules.suppliers import create_supplier_debt_for_stock_in

            debt = await create_supplier_debt_for_stock_in(
                self.session,
                supplier_id=supplier_id,
                stock_transaction_id=transaction.id,
                document_no=document_no,
                original_amount=total,
                paid_amount=paid,
                currency=transaction.currency,
                exchange_rate=transaction.exchange_rate,
            )

        # paid_amount > 0 → immutable payment record (spec 2.1.x Stock In).
        # Attached to the created debt when partial, otherwise to the purchase.
        if paid > 0:
            from app.modules.pos.models import Payment

            self.session.add(
                Payment(
                    payment_no=await allocate_document_number(self.session, "SUPPLIER_DEBT_PAYMENT"),
                    sale_id=None,
                    supplier_id=supplier_id,
                    supplier_debt_id=debt.id if debt is not None else None,
                    payment_type="SUPPLIER_DEBT_PAYMENT" if debt is not None else "STOCK_IN_PAYMENT",
                    payment_method=payload.payment_method or "CASH",
                    amount=paid,
                    reference_no=payload.reference_no or document_no,
                    note=payload.note,
                    created_by=actor.id,
                )
            )
            await self.session.flush()

        await record_audit(
            self.session,
            action="stock_in",
            module="stock",
            user_id=actor.id,
            entity_type="stock_transaction",
            entity_id=transaction.id,
            new_values={
                "document_no": document_no,
                "subtotal": str(subtotal),
                "discount": str(discount),
                "tax": str(tax),
                "total": str(total),
                "paid": str(paid),
            },
        )
        await self.session.commit()

        # Telegram purchase notification strictly AFTER commit: a delivery
        # failure must never roll back the Stock In.
        supplier_name = None
        if transaction.supplier_id:
            from app.modules.suppliers.models import Supplier

            supplier = await self.session.get(Supplier, transaction.supplier_id)
            supplier_name = supplier.name if supplier else None
        from app.shared.telegram.service import notify_purchase

        await notify_purchase(
            self.session,
            document_no=document_no,
            occurred_at=transaction.transaction_date,
            supplier=supplier_name,
            currency=transaction.currency,
            exchange_rate=transaction.exchange_rate,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            total=total,
            paid=paid,
            debt=(total - paid) if total > paid else Decimal("0.00"),
            user=actor.full_name,
            item_count=len(item_rows),
            # `quantity`/`unit_cost` are stored per BASE UOM, so the row omits
            # the entered UOM symbol (base quantity × base cost = line total).
            items=[
                {
                    "name": products[item.product_id].name,
                    "quantity": str(item.quantity),
                    "uom": "",
                    "unit_cost": str(item.unit_cost),
                    "line_total": str(item.line_total),
                }
                for item in item_rows
            ],
        )
        return self._operation_out(transaction, items=item_rows, total_amount=total, paid_amount=paid, debt=debt)

    async def update_purchase(self, stock_transaction_id, payload, *, actor: User) -> StockOperationOut:
        """Edit a confirmed Stock In: reverse the original received quantities
        (batch + compensating PURCHASE_RETURN movements) then receive the new
        lines. The supplier and immutable payments stay; the outstanding
        supplier debt is recalculated from the new total."""
        result = await self.session.execute(
            select(StockTransaction)
            .where(StockTransaction.id == stock_transaction_id)
            .with_for_update()
        )
        transaction = result.scalar_one_or_none()
        if transaction is None:
            raise NotFoundError("Stock In not found")
        if transaction.transaction_type != "STOCK_IN":
            raise ConflictError("Only Stock In documents can be edited")
        existing_items = list(transaction.items)
        if any(Decimal(item.returned_quantity or 0) > 0 for item in existing_items):
            raise ConflictError("Stock In documents with purchase returns cannot be edited")

        old_subtotal = sum((Decimal(item.line_total) for item in existing_items), Decimal("0.00"))
        old_total = (
            old_subtotal - _q2(transaction.discount_amount) + _q2(transaction.tax_amount)
        ).quantize(TWO, rounding=ROUND_HALF_UP)

        products: dict = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in request", field_errors={"items": "Duplicate product"})
            products[item.product_id] = await self._get_product(item.product_id)

        negative_ok = await allow_negative_stock(self.session)

        from app.modules.stock import batch_service

        # Resolve every requested line to base-UOM amounts (same rules as
        # stock_in) before touching stock, so a validation failure rolls back.
        specs: list[dict] = []
        for item in payload.items:
            product = products[item.product_id]
            if product.track_batch:
                if not (item.batch_no or "").strip():
                    raise ValidationError(
                        "Batch number is required for batch-tracked products",
                        field_errors={"items": "Batch number is required"},
                    )
                if product.expiry_tracking and item.expiry_date is None:
                    raise ValidationError(
                        "Expiry date is required for expiry-tracked products",
                        field_errors={"items": "Expiry date is required"},
                    )
            factor = item.factor_to_base
            if item.uom_id is not None:
                if str(item.uom_id) == str(product.uom_id):
                    factor = Decimal("1")
                else:
                    conversion = next(
                        (row for row in (product.uom_conversions or []) if str(row.get("uom_id")) == str(item.uom_id)),
                        None,
                    )
                    if conversion is None:
                        raise ValidationError(
                            "The selected UOM is not a Pricing UOM of this product",
                            field_errors={"items": "Invalid UOM"},
                        )
                    row_factor = Decimal(str(conversion.get("factor_to_base", 1)))
                    if factor is not None and Decimal(str(factor)) != row_factor:
                        raise ValidationError(
                            "factor_to_base does not match the product's Pricing row",
                            field_errors={"items": "Invalid factor"},
                        )
                    factor = row_factor
            if factor is None:
                factor = Decimal("1")
            if factor <= 0:
                raise ValidationError("factor_to_base must be greater than zero", field_errors={"items": "Invalid factor"})
            base_quantity = _q4(Decimal(item.quantity) * factor)
            if base_quantity <= 0:
                raise ValidationError("Line quantity must be greater than zero", field_errors={"items": "Invalid quantity"})
            base_unit_cost = (Decimal(item.unit_cost) / factor).quantize(TWO, rounding=ROUND_HALF_UP)
            specs.append({
                "product": product,
                "product_id": item.product_id,
                "base_quantity": base_quantity,
                "base_unit_cost": base_unit_cost,
                "ledger_unit_cost": _usd_unit_cost(base_unit_cost, payload.currency, payload.exchange_rate),
                "line_total": (Decimal(item.quantity) * Decimal(item.unit_cost)).quantize(TWO, rounding=ROUND_HALF_UP),
                "batch_no": item.batch_no,
                "expiry_date": item.expiry_date,
                "uom_symbol": (
                    item.uom_symbol
                    or (product.uom_ref.symbol if item.uom_id is None and product.uom_ref else None)
                ),
            })

        def _line_key(product_id, batch_no, expiry_date) -> tuple[str, str, str]:
            return (str(product_id or ""), str(batch_no or ""), str(expiry_date or ""))

        existing_by_key = {
            _line_key(row.product_id, row.batch_no, row.expiry_date): row for row in existing_items
        }

        async def _take_back(*, product, product_id, batch_no, expiry_date, quantity, unit_cost, uom_symbol):
            """Take `quantity` base units back out of a line's lot (edit
            decrease / removed line), failing clearly when the stock is gone."""
            available = await batch_service.available_quantity(
                self.session, product_id=product_id, batch_no=batch_no, expiry_date=expiry_date
            )
            if available < quantity:
                raise ValidationError(
                    f"Cannot reduce below what is still in stock: available {available}, requested {quantity}",
                    field_errors={"items": "Insufficient stock"},
                )
            movement_batch_id = None
            movement_expiry = None
            if (batch_no or "").strip():
                batch = await batch_service.deduct_from_batch(
                    self.session,
                    product_id=product_id,
                    batch_no=batch_no,
                    quantity_base=quantity,
                    expiry_date=expiry_date,
                )
                movement_batch_id = batch.id
                movement_expiry = batch.expiry_date
            else:
                allocations = await batch_service.allocate_fefo(
                    self.session,
                    product=product,
                    quantity_base=quantity,
                    allow_negative=negative_ok,
                    include_expired=True,
                )
                await batch_service.deduct_allocations(self.session, allocations)
            await apply_stock_movement(
                self.session,
                product_id=product_id,
                movement_type="PURCHASE_RETURN",
                quantity_delta=-quantity,
                unit_cost=unit_cost,
                reference_type="stock_transaction",
                reference_id=transaction.id,
                created_by=actor.id,
                document_no=transaction.document_no,
                batch_no=batch_no,
                batch_id=movement_batch_id,
                expiry_date=movement_expiry,
                allow_negative=negative_ok,
                uom_symbol=uom_symbol,
            )

        # Apply the DIFFERENCE per line: price/note-only edits never move
        # stock; an increase receives the extra; a decrease takes it back out.
        total = Decimal("0.00")
        item_rows: list[StockTransactionItem] = []
        matched_ids: set[uuid.UUID] = set()
        for spec in specs:
            existing = existing_by_key.get(
                _line_key(spec["product_id"], spec["batch_no"], spec["expiry_date"])
            )
            if existing is not None:
                matched_ids.add(existing.id)
                delta = _q4(spec["base_quantity"] - _q4(existing.quantity))
                if delta > 0:
                    batch_lot = await batch_service.batch_in(
                        self.session,
                        product_id=spec["product_id"],
                        batch_no=spec["batch_no"],
                        expiry_date=spec["expiry_date"],
                        quantity_base=delta,
                        unit_cost_per_base=spec["ledger_unit_cost"],
                        supplier_id=transaction.supplier_id,
                        document_no=transaction.document_no,
                    )
                    await apply_stock_movement(
                        self.session,
                        product_id=spec["product_id"],
                        movement_type="STOCK_IN",
                        quantity_delta=delta,
                        unit_cost=spec["ledger_unit_cost"],
                        reference_type="stock_transaction",
                        reference_id=transaction.id,
                        created_by=actor.id,
                        document_no=transaction.document_no,
                        batch_no=batch_lot.batch_no or None,
                        batch_id=batch_lot.id if (batch_lot.batch_no or "").strip() else None,
                        expiry_date=spec["expiry_date"],
                        allow_negative=negative_ok,
                        uom_symbol=spec["uom_symbol"],
                    )
                elif delta < 0:
                    await _take_back(
                        product=spec["product"],
                        product_id=spec["product_id"],
                        batch_no=spec["batch_no"],
                        expiry_date=spec["expiry_date"],
                        quantity=-delta,
                        unit_cost=spec["ledger_unit_cost"],
                        uom_symbol=spec["uom_symbol"],
                    )
                existing.product_name = spec["product"].name
                existing.quantity = spec["base_quantity"]
                existing.unit_cost = spec["base_unit_cost"]
                existing.batch_no = spec["batch_no"]
                existing.expiry_date = spec["expiry_date"]
                existing.uom_symbol = spec["uom_symbol"]
                existing.line_total = spec["line_total"]
                item_rows.append(existing)
                total += spec["line_total"]
            else:
                row = StockTransactionItem(
                    stock_transaction_id=transaction.id,
                    product_id=spec["product_id"],
                    product_ref=spec["product"],
                    product_name=spec["product"].name,
                    quantity=spec["base_quantity"],
                    unit_cost=spec["base_unit_cost"],
                    batch_no=spec["batch_no"],
                    expiry_date=spec["expiry_date"],
                    uom_symbol=spec["uom_symbol"],
                    line_total=spec["line_total"],
                )
                item_rows.append(row)
                self.session.add(row)
                batch_lot = await batch_service.batch_in(
                    self.session,
                    product_id=spec["product_id"],
                    batch_no=spec["batch_no"],
                    expiry_date=spec["expiry_date"],
                    quantity_base=spec["base_quantity"],
                    unit_cost_per_base=spec["ledger_unit_cost"],
                    supplier_id=transaction.supplier_id,
                    document_no=transaction.document_no,
                )
                # batch_in may have auto-assigned the next batch number (a
                # reused batch_no with a different expiry): record the real one.
                row.batch_no = batch_lot.batch_no or None
                await apply_stock_movement(
                    self.session,
                    product_id=spec["product_id"],
                    movement_type="STOCK_IN",
                    quantity_delta=spec["base_quantity"],
                    unit_cost=spec["ledger_unit_cost"],
                    reference_type="stock_transaction",
                    reference_id=transaction.id,
                    created_by=actor.id,
                    document_no=transaction.document_no,
                    batch_no=batch_lot.batch_no or None,
                    batch_id=batch_lot.id if (batch_lot.batch_no or "").strip() else None,
                    expiry_date=spec["expiry_date"],
                    allow_negative=negative_ok,
                    uom_symbol=spec["uom_symbol"],
                )
                total += spec["line_total"]

        # Lines dropped from the purchase: take the original quantity back out.
        for existing in existing_items:
            if existing.id in matched_ids:
                continue
            quantity = _q4(existing.quantity)
            if quantity > 0 and existing.product_id is not None:
                await _take_back(
                    product=existing.product_ref,
                    product_id=existing.product_id,
                    batch_no=existing.batch_no,
                    expiry_date=existing.expiry_date,
                    quantity=quantity,
                    unit_cost=_usd_unit_cost(
                        existing.unit_cost, transaction.currency, transaction.exchange_rate
                    ),
                    uom_symbol=existing.uom_symbol,
                )
            await self.session.delete(existing)
        await self.session.flush()

        subtotal = total.quantize(TWO, rounding=ROUND_HALF_UP)
        discount = _q2(payload.discount_amount or 0)
        tax = _q2(payload.tax_amount or 0)
        if discount > subtotal:
            raise ValidationError(
                "Discount cannot exceed the line subtotal",
                field_errors={"discount_amount": "Discount exceeds subtotal"},
            )
        new_total = (subtotal - discount + tax).quantize(TWO, rounding=ROUND_HALF_UP)

        transaction.transaction_date = self._resolve_date(payload.transaction_date)
        transaction.reference_no = payload.reference_no
        transaction.note = payload.note
        transaction.discount_amount = discount
        transaction.tax_amount = tax
        transaction.currency = payload.currency
        transaction.exchange_rate = payload.exchange_rate

        # 3) Recalculate the outstanding supplier debt (payments stay immutable).
        debt_result = await self.session.execute(
            select(SupplierDebt)
            .where(SupplierDebt.stock_transaction_id == transaction.id)
            .with_for_update()
        )
        debt = debt_result.scalars().first()
        existing_paid = _q2(debt.paid_amount) if debt is not None else _q2(old_total)
        paid = max(Decimal("0.00"), min(existing_paid, new_total))
        outstanding = new_total - paid
        if outstanding > 0 and transaction.supplier_id is None:
            raise ValidationError(
                "Full payment is required when no supplier is selected",
                field_errors={"paid_amount": "Full payment required"},
            )
        if debt is not None:
            debt.original_amount = new_total
            debt.paid_amount = paid
            debt.remaining_amount = outstanding
            debt.status = "PAID" if outstanding == 0 else ("PARTIAL" if paid > 0 else "UNPAID")
            debt.currency = transaction.currency
            debt.exchange_rate = transaction.exchange_rate
        elif outstanding > 0:
            from app.modules.suppliers import create_supplier_debt_for_stock_in

            debt = await create_supplier_debt_for_stock_in(
                self.session,
                supplier_id=transaction.supplier_id,
                stock_transaction_id=transaction.id,
                document_no=transaction.document_no,
                original_amount=new_total,
                paid_amount=paid,
                currency=transaction.currency,
                exchange_rate=transaction.exchange_rate,
            )

        await record_audit(
            self.session,
            action="stock_in_update",
            module="stock",
            user_id=actor.id,
            entity_type="stock_transaction",
            entity_id=transaction.id,
            new_values={
                "document_no": transaction.document_no,
                "subtotal": str(subtotal),
                "discount": str(discount),
                "tax": str(tax),
                "total": str(new_total),
                "paid": str(paid),
            },
        )
        await self.session.commit()
        return self._operation_out(transaction, items=item_rows, total_amount=new_total, paid_amount=paid, debt=debt)

    async def purchase_return(self, stock_transaction_id: uuid.UUID, payload, *, actor: User):
        """Return to supplier (spec: Purchase Return Transaction).

        One transaction: lock the stock-in + its lines, validate returnable
        qty (received − returned) and available stock, allocate the PRT-
        sequence, create the immutable purchase_returns/items, stock OUT via
        the canonical mutation (PURCHASE_RETURN), reduce the supplier debt
        for that purchase (or record a supplier credit when fully paid),
        audit, and commit — or roll everything back."""
        from app.modules.pos.models import Payment

        result = await self.session.execute(
            select(StockTransaction)
            .where(StockTransaction.id == stock_transaction_id)
            .with_for_update()
        )
        transaction = result.scalar_one_or_none()
        if transaction is None:
            raise NotFoundError("Stock In document not found")
        if transaction.transaction_type != "STOCK_IN" or transaction.status != "CONFIRMED":
            raise ConflictError("Only confirmed Stock In documents can be returned")

        items_by_id: dict[uuid.UUID, StockTransactionItem] = {
            item.id: item for item in transaction.items
        }
        # Sum requested quantities per line first: duplicate stock_transaction_
        # item_id rows must be validated as a whole, never each independently.
        requested: dict[uuid.UUID, Decimal] = {}
        for line in payload.lines:
            item = items_by_id.get(line.stock_transaction_item_id)
            if item is None:
                raise NotFoundError("Stock In line not found on this document")
            requested[line.stock_transaction_item_id] = (
                requested.get(line.stock_transaction_item_id, Decimal("0")) + Decimal(line.quantity)
            )
        from app.modules.stock import batch_service

        for item_id, total_quantity in requested.items():
            item = items_by_id[item_id]
            returnable = Decimal(item.quantity) - Decimal(item.returned_quantity)
            if total_quantity > returnable:
                raise ValidationError(
                    f"Cannot return more than the returnable quantity ({returnable})",
                    field_errors={"lines": "Return quantity exceeds returnable"},
                )
            # Only stock still physically on hand can be returned to the
            # supplier — a lot that was already sold/disposed cannot.
            if item.product_id is not None:
                available = await batch_service.available_quantity(
                    self.session,
                    product_id=item.product_id,
                    batch_no=item.batch_no,
                    expiry_date=item.expiry_date,
                )
                if total_quantity > available:
                    raise ValidationError(
                        f"Return quantity exceeds the quantity in stock ({available})",
                        field_errors={"lines": "Return quantity exceeds in-stock quantity"},
                    )

        negative_ok = await allow_negative_stock(self.session)
        return_no = await allocate_document_number(self.session, "PURCHASE_RETURN")
        purchase_return = PurchaseReturn(
            return_no=return_no,
            stock_transaction_id=transaction.id,
            supplier_id=transaction.supplier_id,
            return_date=payload.return_date or datetime.now(timezone.utc),
            refund_amount=Decimal("0.00"),
            reason=payload.reason,
            created_by=actor.id,
        )
        self.session.add(purchase_return)
        await self.session.flush()

        refund_total = Decimal("0.00")
        out_rows: list[PurchaseReturnItem] = []
        for line in payload.lines:
            item = items_by_id[line.stock_transaction_item_id]
            refund = (Decimal(line.quantity) * Decimal(item.unit_cost)).quantize(TWO, rounding=ROUND_HALF_UP)
            row = PurchaseReturnItem(
                purchase_return_id=purchase_return.id,
                stock_transaction_item_id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=_q4(line.quantity),
                unit_cost=Decimal(item.unit_cost).quantize(TWO, rounding=ROUND_HALF_UP),
                line_refund=refund,
            )
            out_rows.append(row)
            self.session.add(row)
            item.returned_quantity = _q4(Decimal(item.returned_quantity) + Decimal(line.quantity))
            # Purchase return deducts the ORIGINAL batch lot the line was
            # received into (batch identity = product + batch_no); it never
            # invents an arbitrary batch. Unbatched lines drain FEFO (writing
            # down expired lots is allowed for disposals).
            from app.modules.stock import batch_service

            movement_batch_id = None
            movement_expiry = None
            if item.batch_no:
                batch = await batch_service.deduct_from_batch(
                    self.session,
                    product_id=item.product_id,
                    batch_no=item.batch_no,
                    quantity_base=Decimal(line.quantity),
                    expiry_date=item.expiry_date,
                )
                movement_batch_id = batch.id
                movement_expiry = batch.expiry_date
            else:
                allocations = await batch_service.allocate_fefo(
                    self.session,
                    product=item.product_ref,
                    quantity_base=Decimal(line.quantity),
                    allow_negative=negative_ok,
                    include_expired=True,
                )
                await batch_service.deduct_allocations(self.session, allocations)
            await apply_stock_movement(
                self.session,
                product_id=item.product_id,
                movement_type="PURCHASE_RETURN",
                quantity_delta=-Decimal(line.quantity),
                unit_cost=item.unit_cost,
                reference_type="purchase_return",
                reference_id=purchase_return.id,
                created_by=actor.id,
                document_no=return_no,
                batch_no=item.batch_no,
                batch_id=movement_batch_id,
                expiry_date=movement_expiry,
                note=payload.reason,
                allow_negative=negative_ok,
                uom_symbol=item.uom_symbol,
            )
            refund_total += refund
        purchase_return.refund_amount = _q2(refund_total)

        # Money: reduce the supplier debt for THIS purchase while it is open;
        # any refund beyond the open debt (fully-paid purchase or overpaid
        # debt) becomes a supplier credit recorded against the document.
        debt_reduction = Decimal("0.00")
        credit_amount = Decimal("0.00")
        if transaction.supplier_id is not None and purchase_return.refund_amount > 0:
            debt_result = await self.session.execute(
                select(SupplierDebt)
                .where(SupplierDebt.stock_transaction_id == transaction.id)
                .with_for_update()
            )
            debt = debt_result.scalar_one_or_none()
            if debt is not None and debt.remaining_amount > 0:
                debt_reduction = min(purchase_return.refund_amount, debt.remaining_amount)
                debt.remaining_amount = debt.remaining_amount - debt_reduction
                debt.paid_amount = debt.original_amount - debt.remaining_amount
                debt.status = "PAID" if debt.remaining_amount == 0 else "PARTIAL"
            credit_amount = purchase_return.refund_amount - debt_reduction
            if credit_amount > 0:
                self.session.add(
                    Payment(
                        payment_no=await allocate_document_number(self.session, "SUPPLIER_DEBT_PAYMENT"),
                        sale_id=None,
                        supplier_id=transaction.supplier_id,
                        supplier_debt_id=debt.id if debt is not None else None,
                        payment_type="SUPPLIER_RETURN_CREDIT",
                        payment_method="CREDIT",
                        amount=credit_amount,
                        reference_no=return_no,
                        note=f"Purchase return credit for {transaction.document_no}",
                        created_by=actor.id,
                    )
                )
                await self.session.flush()
        purchase_return.debt_reduction = _q2(debt_reduction)
        purchase_return.credit_amount = _q2(credit_amount)

        await record_audit(
            self.session,
            action="purchase_return",
            module="stock",
            user_id=actor.id,
            entity_type="purchase_return",
            entity_id=purchase_return.id,
            new_values={
                "return_no": return_no,
                "document_no": transaction.document_no,
                "refund_amount": str(purchase_return.refund_amount),
                "debt_reduction": str(purchase_return.debt_reduction),
                "credit_amount": str(purchase_return.credit_amount),
            },
        )
        await self.session.commit()

        return PurchaseReturnOut(
            id=purchase_return.id,
            return_no=purchase_return.return_no,
            stock_transaction_id=transaction.id,
            document_no=transaction.document_no,
            supplier_id=transaction.supplier_id,
            return_date=purchase_return.return_date,
            refund_amount=purchase_return.refund_amount,
            debt_reduction=purchase_return.debt_reduction,
            credit_amount=purchase_return.credit_amount,
            reason=purchase_return.reason,
            items=[
                PurchaseReturnItemOut(
                    id=row.id,
                    stock_transaction_item_id=row.stock_transaction_item_id,
                    product_id=row.product_id,
                    product_name=items_by_id[row.stock_transaction_item_id].product_name,
                    quantity=row.quantity,
                    unit_cost=row.unit_cost,
                    line_refund=row.line_refund,
                )
                for row in out_rows
            ],
        )

    async def adjust(self, payload, *, actor: User) -> StockOperationOut:
        return await self._apply_counted_operation(payload, actor=actor, kind="ADJUSTMENT")

    async def damage(self, payload, *, actor: User) -> StockOperationOut:
        return await self._apply_outbound_operation(payload, actor=actor, kind="DAMAGE")

    async def expire(self, payload, *, actor: User) -> StockOperationOut:
        return await self._apply_outbound_operation(payload, actor=actor, kind="EXPIRE")

    async def _apply_counted_operation(self, payload, *, actor: User, kind: str) -> StockOperationOut:
        products: dict = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in request", field_errors={"items": "Duplicate product"})
            products[item.product_id] = await self._get_product(item.product_id)

        document_type = "STOCK_ADJUSTMENT" if kind == "ADJUSTMENT" else kind
        negative_ok = await allow_negative_stock(self.session)
        document_no = await allocate_document_number(self.session, document_type)
        transaction = await self._create_transaction(
            transaction_type=kind, document_no=document_no, payload=payload, actor=actor
        )

        total = Decimal("0.00")
        item_rows: list[StockTransactionItem] = []
        for item in payload.items:
            balance = await _lock_balance(self.session, item.product_id)
            system_quantity = (
                item.system_quantity if item.system_quantity is not None else balance.quantity
            )
            difference = item.actual_quantity - system_quantity
            product = products[item.product_id]
            unit_cost = balance.average_cost
            if difference < 0:
                unit_cost = await resolve_outbound_unit_cost(
                    self.session, product, -difference, fallback=balance.average_cost
                )

            line_total = (abs(difference) * unit_cost).quantize(TWO, rounding=ROUND_HALF_UP)
            row = StockTransactionItem(
                    stock_transaction_id=transaction.id,
                    product_id=item.product_id,
                product_ref=product,
                product_name=product.name,
                quantity=difference,
                unit_cost=unit_cost,
                system_quantity=system_quantity,
                actual_quantity=item.actual_quantity,
                reason=item.reason,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
            if difference != 0:
                from app.modules.stock import batch_service

                # Keep the per-batch ledger in step with the total balance:
                # a count surplus lands in the synthetic unbatched lot, a
                # shortfall drains FEFO (expired lots may be written down).
                if difference > 0:
                    await batch_service.batch_in(
                        self.session,
                        product_id=item.product_id,
                        batch_no=None,
                        expiry_date=None,
                        quantity_base=difference,
                        unit_cost_per_base=unit_cost,
                        document_no=document_no,
                    )
                else:
                    allocations = await batch_service.allocate_fefo(
                        self.session,
                        product=product,
                        quantity_base=-difference,
                        allow_negative=negative_ok,
                        include_expired=True,
                    )
                    await batch_service.deduct_allocations(self.session, allocations)
                await apply_stock_movement(
                    self.session,
                    product_id=item.product_id,
                    movement_type="ADJUSTMENT_IN" if difference > 0 else "ADJUSTMENT_OUT",
                    quantity_delta=difference,
                    unit_cost=unit_cost,
                    reference_type="stock_transaction",
                    reference_id=transaction.id,
                    created_by=actor.id,
                    document_no=document_no,
                    note=item.reason,
                    allow_negative=negative_ok,
                )
            total += line_total

        await record_audit(
            self.session,
            action="stock_adjustment",
            module="stock",
            user_id=actor.id,
            entity_type="stock_transaction",
            entity_id=transaction.id,
            new_values={"document_no": document_no, "total": str(total.quantize(TWO))},
        )
        await self.session.commit()
        return self._operation_out(
            transaction, items=item_rows, total_amount=total.quantize(TWO), paid_amount=total.quantize(TWO)
        )

    async def _apply_outbound_operation(self, payload, *, actor: User, kind: str) -> StockOperationOut:
        products: dict = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in request", field_errors={"items": "Duplicate product"})
            product = await self._get_product(item.product_id)
            if kind == "EXPIRE" and not product.expiry_tracking:
                raise ValidationError(
                    "Expiry tracking is not enabled for this product",
                    field_errors={"items": "Product does not track expiry"},
                )
            products[item.product_id] = product

        negative_ok = await allow_negative_stock(self.session)
        document_type = {"DAMAGE": "STOCK_DAMAGE", "EXPIRE": "STOCK_EXPIRE"}[kind]
        document_no = await allocate_document_number(self.session, document_type)
        transaction = await self._create_transaction(
            transaction_type=kind, document_no=document_no, payload=payload, actor=actor
        )

        total = Decimal("0.00")
        item_rows: list[StockTransactionItem] = []
        for item in payload.items:
            product = products[item.product_id]
            # ---- entered UOM → base quantity (server-resolved factor) ----
            from app.modules.stock import batch_service

            factor = batch_service.factor_for_uom(product, item.uom_id)
            if (
                item.factor_to_base is not None
                and Decimal(str(item.factor_to_base)) != factor
            ):
                raise ValidationError(
                    "factor_to_base does not match the product's Pricing row",
                    field_errors={"factor_to_base": "Invalid factor"},
                )
            base_quantity = _q4(Decimal(item.quantity) * factor)
            if base_quantity <= 0:
                raise ValidationError(
                    "Line quantity must be greater than zero",
                    field_errors={"quantity": "Invalid quantity"},
                )
            entered_uom_id = item.uom_id if item.uom_id is not None else product.uom_id
            entered_uom_symbol = item.uom_symbol or (
                product.uom_ref.symbol if product.uom_ref else None
            )
            entered_qty = _q4(item.quantity)
            balance = await _lock_balance(self.session, item.product_id)
            if item.unit_cost is not None:
                # Entered cost is per the selected UOM → convert to per-base.
                unit_cost = (Decimal(item.unit_cost) / factor).quantize(TWO, rounding=ROUND_HALF_UP)
            else:
                unit_cost = await resolve_outbound_unit_cost(
                    self.session,
                    product,
                    base_quantity,
                    fallback=balance.average_cost,
                )
            line_total = (base_quantity * unit_cost).quantize(TWO, rounding=ROUND_HALF_UP)
            reason = getattr(item, "reason", None)
            # Batch-tracked products (spec): Damage/Expiry must operate on a
            # specific batch — never an arbitrary drain of the product total.
            if product.track_batch and not (item.batch_no or "").strip():
                raise ValidationError(
                    "Batch number is required for batch-tracked products",
                    field_errors={"items": "Batch number is required"},
                )
            # Validate + deduct the named batch lot (when the caller names
            # one). Unbatched damage/expiry drains FEFO (disposals may write
            # down expired lots; sales never can).
            movement_batch_id = None
            if item.batch_no:
                batch = await batch_service.deduct_from_batch(
                    self.session,
                    product_id=item.product_id,
                    batch_no=item.batch_no,
                    quantity_base=base_quantity,
                    expiry_date=getattr(item, "expiry_date", None),
                )
                movement_batch_id = batch.id
            else:
                allocations = await batch_service.allocate_fefo(
                    self.session,
                    product=product,
                    quantity_base=base_quantity,
                    allow_negative=negative_ok,
                    include_expired=True,
                )
                await batch_service.deduct_allocations(self.session, allocations)
            row = StockTransactionItem(
                    stock_transaction_id=transaction.id,
                    product_id=item.product_id,
                product_ref=product,
                product_name=product.name,
                quantity=base_quantity,
                unit_cost=unit_cost,
                batch_no=item.batch_no,
                expiry_date=getattr(item, "expiry_date", None),
                entered_uom_id=entered_uom_id,
                entered_uom_symbol=entered_uom_symbol,
                entered_factor_to_base=factor,
                entered_quantity=entered_qty,
                reason=reason,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
            await apply_stock_movement(
                self.session,
                product_id=item.product_id,
                movement_type=kind,
                quantity_delta=-base_quantity,
                unit_cost=unit_cost,
                reference_type="stock_transaction",
                reference_id=transaction.id,
                created_by=actor.id,
                document_no=document_no,
                batch_no=item.batch_no,
                batch_id=movement_batch_id,
                expiry_date=getattr(item, "expiry_date", None),
                note=reason,
                allow_negative=negative_ok,
                uom_symbol=entered_uom_symbol,
            )
            total += line_total

        await record_audit(
            self.session,
            action="stock_damage" if kind == "DAMAGE" else "stock_expire",
            module="stock",
            user_id=actor.id,
            entity_type="stock_transaction",
            entity_id=transaction.id,
            new_values={"document_no": document_no, "total_loss": str(total.quantize(TWO))},
        )
        await self.session.commit()
        return self._operation_out(
            transaction, items=item_rows, total_amount=total.quantize(TWO), paid_amount=total.quantize(TWO)
        )

    async def quick_operation(self, *, payload, actor: User) -> dict:
        """Single-product quick operation from the Stock list
        (POST /stock/operations): stock_in | adjustment | damage | expiry.
        Reuses the canonical transactional operations; never writes balances."""
        operation_type = (payload.type or "stock_in").strip().lower()
        product = await self._get_product(payload.product_id)
        # Server-side factor resolution (spec: never trust a frontend
        # factor). A line without a UOM is the base UOM; an explicit factor
        # must match the product's Pricing row.
        from app.modules.stock import batch_service

        factor = batch_service.factor_for_uom(product, payload.uom_id)
        if (
            payload.factor_to_base is not None
            and Decimal(str(payload.factor_to_base)) != factor
        ):
            raise ValidationError(
                "factor_to_base does not match the product's Pricing row",
                field_errors={"factor_to_base": "Invalid factor"},
            )
        base_quantity = (Decimal(payload.quantity) * factor).quantize(Decimal("0.0001"))

        if operation_type == "stock_in":
            if base_quantity <= 0:
                raise ValidationError("Quantity must be greater than zero")
            balance = await self.repo.ensure_balance(product.id)
            if payload.unit_cost is not None:
                # unitCost is per selected UOM; the ledger keeps the base-unit cost.
                unit_cost = (Decimal(str(payload.unit_cost)) / factor).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                unit_cost = balance.average_cost or Decimal("0.00")
            base_quantity_abs = abs(base_quantity)
            line_total = (base_quantity_abs * unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            request = StockInRequest(
                transaction_date=payload.transaction_date,
                note=payload.note,
                paid_amount=line_total,
                items=[
                    StockInItem(
                        product_id=product.id,
                        quantity=base_quantity_abs,
                        unit_cost=unit_cost,
                        batch_no=None,
                        expiry_date=None,
                        uom_symbol=payload.uom_symbol,
                    )
                ],
            )
            result = await self.stock_in(request, actor=actor)
        elif operation_type == "adjustment":
            if Decimal(payload.quantity) == 0:
                raise ValidationError("Quantity cannot be zero")
            balance = await self.repo.ensure_balance(product.id)
            request = StockAdjustmentRequest(
                transaction_date=payload.transaction_date,
                note=payload.note,
                items=[
                    AdjustmentItem(
                        product_id=product.id,
                        system_quantity=balance.quantity,
                        actual_quantity=balance.quantity + Decimal(payload.quantity),
                        reason=payload.note or "Quick adjustment",
                    )
                ],
            )
            result = await self.adjust(request, actor=actor)
        elif operation_type in ("damage", "expiry"):
            if base_quantity <= 0:
                raise ValidationError("Quantity must be greater than zero")
            if operation_type == "expiry":
                request = StockExpireRequest(
                    transaction_date=payload.transaction_date,
                    note=payload.note,
                    items=[
                        ExpireItem(
                            product_id=product.id,
                            quantity=base_quantity,
                            unit_cost=None,
                            reason=payload.note or "Expired",
                            note=payload.note,
                        )
                    ],
                )
                result = await self.expire(request, actor=actor)
            else:
                request = StockDamageRequest(
                    transaction_date=payload.transaction_date,
                    note=payload.note,
                    items=[
                        DamageItem(
                            product_id=product.id,
                            quantity=base_quantity,
                            unit_cost=None,
                            reason=payload.note or "Damaged",
                        )
                    ],
                )
                result = await self.damage(request, actor=actor)
        else:
            raise ValidationError(f"Unknown stock operation type '{operation_type}'")

        return {
            "id": result.id,
            "document_no": result.document_no,
            "reference": result.document_no,
            "type": operation_type,
            "product": product.name,
            "product_id": product.id,
            "quantity": payload.quantity,
            "total_amount": result.total_amount,
        }

    async def list_operations(self, *, q, operation_type, supplier_id, status, start, end, page, limit):
        """Stock operation documents (GET /stock/operations) — the read model
        behind the Stock In / purchase list and the Cost Price history dialog."""
        from app.shared.pagination.params import parse_date_range

        stmt = select(StockTransaction)
        count_stmt = select(func.count()).select_from(StockTransaction)
        if operation_type and operation_type != "all":
            stmt = stmt.where(StockTransaction.transaction_type == operation_type)
            count_stmt = count_stmt.where(StockTransaction.transaction_type == operation_type)
        if supplier_id is not None:
            stmt = stmt.where(StockTransaction.supplier_id == supplier_id)
            count_stmt = count_stmt.where(StockTransaction.supplier_id == supplier_id)
        if status:
            stmt = stmt.where(StockTransaction.status == status)
            count_stmt = count_stmt.where(StockTransaction.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(StockTransaction.document_no.ilike(pattern))
            count_stmt = count_stmt.where(StockTransaction.document_no.ilike(pattern))
        start_at, end_at = parse_date_range(start, end)
        if start_at is not None:
            stmt = stmt.where(StockTransaction.transaction_date >= start_at)
            count_stmt = count_stmt.where(StockTransaction.transaction_date >= start_at)
        if end_at is not None:
            stmt = stmt.where(StockTransaction.transaction_date <= end_at)
            count_stmt = count_stmt.where(StockTransaction.transaction_date <= end_at)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(StockTransaction.transaction_date.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        transactions = list(rows.scalars().all())
        return transactions, int(total)

    def operation_document_out(self, transaction: StockTransaction, supplier_name: str | None) -> dict:
        """Document row with items (camelCase keys the dialogs read)."""
        total = sum((item.line_total for item in transaction.items), Decimal("0")).quantize(TWO)
        return {
            "id": transaction.id,
            "document_no": transaction.document_no,
            "purchaseNo": transaction.document_no,
            "type": transaction.transaction_type,
            "date": transaction.transaction_date,
            "transaction_date": transaction.transaction_date,
            "supplier_id": transaction.supplier_id,
            "supplier": supplier_name,
            "status": transaction.status,
            "reference_no": transaction.reference_no,
            "note": transaction.note,
            "total": total,
            "created_at": transaction.created_at,
            "items": [
                {
                    "id": item.id,
                    "product_id": item.product_id,
                    "productId": item.product_id,
                    "name": item.product_name or (item.product_ref.name if item.product_ref else None),
                    "price": item.unit_cost,
                    "unit_cost": item.unit_cost,
                    "quantity": item.quantity,
                    "uom_symbol": item.uom_symbol,
                    "batch_no": item.batch_no,
                    "expiry_date": item.expiry_date,
                    "line_total": item.line_total,
                }
                for item in transaction.items
            ],
        }

    def _operation_out(
        self, transaction, *, items: list[StockTransactionItem], total_amount, paid_amount, debt=None
    ) -> StockOperationOut:
        return StockOperationOut(
            id=transaction.id,
            document_no=transaction.document_no,
            transaction_type=transaction.transaction_type,
            supplier_id=transaction.supplier_id,
            transaction_date=transaction.transaction_date,
            reference_no=transaction.reference_no,
            note=transaction.note,
            status=transaction.status,
            total_amount=total_amount,
            paid_amount=paid_amount,
            discount_amount=transaction.discount_amount,
            tax_amount=transaction.tax_amount,
            currency=transaction.currency,
            exchange_rate=transaction.exchange_rate,
            debt_created=debt is not None,
            debt_id=debt.id if debt is not None else None,
            items=[
                OperationItemOut(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=item.product_name or (item.product_ref.name if item.product_ref else None),
                    uom_symbol=item.uom_symbol,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    returned_quantity=item.returned_quantity,
                    system_quantity=item.system_quantity,
                    actual_quantity=item.actual_quantity,
                    batch_no=item.batch_no,
                    expiry_date=item.expiry_date,
                    reason=item.reason,
                    line_total=item.line_total,
                    entered_quantity=item.entered_quantity,
                    entered_uom_symbol=item.entered_uom_symbol,
                    entered_factor_to_base=item.entered_factor_to_base,
                )
                for item in items
            ],
        )

    # ------------------------------------------------------------------ reads

    async def list_movements(self, *, q, product_id, movement_type, start, end, page, limit, sort=None):
        """Read-only movement ledger listing (Stock Movements page).

        Filters: q (document no / note), product, movement type, date range.
        Sort: `field` / `-field` on createdAt | quantity_delta; newest first
        by default. Rows are read-only.
        """
        from app.shared.pagination.params import parse_date_range

        if movement_type:
            normalized = movement_type.strip().upper()
            if normalized not in MOVEMENT_TYPES:
                raise ValidationError(
                    f"Unknown movement type '{movement_type}'",
                    field_errors={"movement_type": "Unknown movement type"},
                )
            movement_type = normalized

        stmt = select(StockMovement, User.full_name).join(
            User, User.id == StockMovement.created_by, isouter=True
        )
        count_stmt = select(func.count()).select_from(StockMovement)
        conditions = []
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(StockMovement.document_no.ilike(pattern) | StockMovement.note.ilike(pattern))
        if product_id is not None:
            conditions.append(StockMovement.product_id == product_id)
        if movement_type:
            conditions.append(StockMovement.movement_type == movement_type)
        start_at, end_at = parse_date_range(start, end)
        if start_at is not None:
            conditions.append(StockMovement.created_at >= start_at)
        if end_at is not None:
            conditions.append(StockMovement.created_at <= end_at)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(*_movement_order_by(sort))
            .offset((page - 1) * limit)
            .limit(limit)
        )
        movements = [(movement, user_name) for movement, user_name in rows.all()]
        return [movement_to_out(m, user_name=u) for m, u in movements], int(total)


def _movement_order_by(sort: str | None) -> tuple:
    """Movement-list sort. `sort` is `field` or `-field` (descending).
    Unknown fields fall back to the ledger default: newest first, id as tiebreak."""
    columns = {
        "createdAt": StockMovement.created_at,
        "created_at": StockMovement.created_at,
        "date": StockMovement.created_at,
        "quantity": StockMovement.quantity_delta,
        "quantity_delta": StockMovement.quantity_delta,
    }
    if sort:
        column = columns.get(sort.lstrip("+-").strip())
        if column is not None:
            if sort.lstrip().startswith("-"):
                return (column.desc(), StockMovement.id.desc())
            return (column.asc(), StockMovement.id.asc())
    return (StockMovement.created_at.desc(), StockMovement.id.desc())


def movement_to_out(
    movement: StockMovement,
    *,
    user_name: str | None = None,
) -> MovementOut:
    """Ledger row → MovementOut (Stock Movements page + history consumers)."""
    delta = movement.quantity_delta
    product = movement.product_ref
    return MovementOut(
        id=movement.id,
        product_id=movement.product_id,
        product_name=movement.product_name or (product.name if product else None),
        barcode=product.barcode if product else None,
        movement_type=movement.movement_type,
        quantity_delta=delta,
        qty_in=delta if delta > 0 else Decimal("0.0000"),
        qty_out=-delta if delta < 0 else Decimal("0.0000"),
        unit_cost=movement.unit_cost,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        document_no=movement.document_no,
        source_reference=movement.document_no,
        batch_no=movement.batch_no,
        batch_id=movement.batch_id,
        expiry_date=movement.expiry_date,
        uom_symbol=movement.uom_symbol
        or (product.uom_ref.symbol if product and product.uom_ref else None),
        note=movement.note,
        user=user_name,
        created_by=movement.created_by,
        created_at=movement.created_at,
    )


async def list_stock_in_transactions_for_supplier(session: AsyncSession, supplier_id, page: int, limit: int):
    """Public interface: supplier purchase/stock-in history.

    Each row carries the user who created the document and the paid/remaining
    amounts so the supplier History tab can mirror the Purchase Report."""
    stmt = (
        select(StockTransaction, User.full_name, SupplierDebt)
        .join(User, User.id == StockTransaction.created_by, isouter=True)
        .outerjoin(SupplierDebt, SupplierDebt.stock_transaction_id == StockTransaction.id)
        .where(StockTransaction.supplier_id == supplier_id, StockTransaction.transaction_type == "STOCK_IN")
        .order_by(StockTransaction.transaction_date.desc())
    )
    count_stmt = (
        select(func.count())
        .select_from(StockTransaction)
        .where(StockTransaction.supplier_id == supplier_id, StockTransaction.transaction_type == "STOCK_IN")
    )
    total = (await session.execute(count_stmt)).scalar_one()
    rows = await session.execute(stmt.offset((page - 1) * limit).limit(limit))
    data = []
    for transaction, user_name, debt in rows.all():
        line_total = sum(
            (item.line_total for item in transaction.items), Decimal("0")
        ).quantize(TWO)
        remaining = Decimal(debt.remaining_amount) if debt else Decimal("0.00")
        paid = (line_total - remaining) if debt else line_total
        data.append(
            {
                "id": str(transaction.id),
                "document_no": transaction.document_no,
                "transaction_date": transaction.transaction_date.isoformat(),
                "reference_no": transaction.reference_no,
                "note": transaction.note,
                "status": debt.status if debt else "PAID",
                "total": str(line_total),
                "paid_amount": str(paid),
                "remaining_amount": str(remaining),
                "currency": transaction.currency,
                "user_name": user_name,
            }
        )
    return data, int(total)
