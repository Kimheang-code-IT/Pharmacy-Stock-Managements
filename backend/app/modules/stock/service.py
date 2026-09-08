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
    """Product master data. Stock quantities are never edited here â€” only the
    canonical stock mutation service may change balances."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProductRepository(session)

    async def list(self, *, q, category_id, status, page, limit) -> tuple[list[dict], int]:
        products, total = await self.repo.list(
            q=q, category_id=category_id, status=status, page=page, limit=limit
        )
        grouped = await self.repo.aggregate_movements([p.id for p in products])
        return [product_to_out(p, grouped=grouped) for p in products], total

    async def get(self, product_id: uuid.UUID) -> dict:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        grouped = await self.repo.aggregate_movements([product.id])
        return product_to_out(product, grouped=grouped)

    async def create(self, payload) -> dict:
        if await self.repo.get_by_sku(payload.sku):
            raise ConflictError("A product with this SKU already exists")
        if payload.barcode and await self.repo.get_by_barcode(payload.barcode):
            raise ConflictError("A product with this barcode already exists")
        await self._validate_category(payload.category_id)
        await self._validate_uom(payload.uom_id)
        await self._validate_brand(payload.brand_id)

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
        self.session.add(product)
        await self.session.flush()
        await self.repo.ensure_balance(product.id)
        # Seed sale-price version 1 (POS-active) so POS always has a versioned price.
        from app.modules.stock import sale_prices as sale_price_service

        await sale_price_service.seed_initial_sale_price(
            self.session, product, actor_id=None
        )
        await self.session.commit()
        await self.session.refresh(product, attribute_names=["category_ref", "brand_ref", "uom_ref", "balance"])
        return product_to_out(product)

    async def update(self, product_id: uuid.UUID, payload, *, actor: User) -> dict:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")

        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        # image_object_key=None explicitly clears the product image.
        if "image_object_key" in payload.model_fields_set and payload.image_object_key is None:
            changes["image_object_key"] = None
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
        if "sku" in changes and changes["sku"] != product.sku:
            if await self.repo.get_by_sku(changes["sku"]):
                raise ConflictError("A product with this SKU already exists")
        if "barcode" in changes and changes["barcode"] and changes["barcode"] != product.barcode:
            if await self.repo.get_by_barcode(changes["barcode"]):
                raise ConflictError("A product with this barcode already exists")
        if "category_id" in changes:
            await self._validate_category(changes["category_id"])
        if "uom_id" in changes:
            await self._validate_uom(changes["uom_id"])
        if "brand_id" in changes:
            await self._validate_brand(changes["brand_id"])

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
        if new_selling_price is not None and Decimal(str(new_selling_price)) != Decimal(str(product.selling_price)):
            from app.modules.stock import sale_prices as sale_price_service

            await sale_price_service.add_sale_price(
                self.session,
                product_id=product.id,
                sale_price=new_selling_price,
                effective_date=None,
                actor=actor,
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
        await self.session.commit()
        await self.session.refresh(product, attribute_names=["category_ref", "brand_ref", "uom_ref", "balance"])
        return product_to_out(product)

    async def delete(self, product_id: uuid.UUID) -> None:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        if await self.repo.count_movements(product.id) > 0:
            raise ConflictError("Cannot delete a product that has stock history")
        balance = await self.repo.ensure_balance(product.id)
        if balance.quantity != 0:
            raise ConflictError("Cannot delete a product that still has stock")
        await self.session.delete(product)
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
        movement_type=movement_type,
        quantity_delta=delta,
        unit_cost=Decimal(unit_cost).quantize(TWO, rounding=ROUND_HALF_UP),
        reference_type=reference_type,
        reference_id=reference_id,
        document_no=document_no,
        batch_no=batch_no,
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
            # unit_cost is per selected UOM; the ledger keeps the base-unit cost.
            base_unit_cost = (Decimal(item.unit_cost) / factor).quantize(TWO, rounding=ROUND_HALF_UP)
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
                quantity=base_quantity,
                unit_cost=base_unit_cost,
                batch_no=item.batch_no,
                expiry_date=item.expiry_date,
                uom_symbol=line_uom_symbol,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
            await apply_stock_movement(
                self.session,
                product_id=item.product_id,
                movement_type="STOCK_IN",
                quantity_delta=base_quantity,
                unit_cost=base_unit_cost,
                reference_type="stock_transaction",
                reference_id=transaction.id,
                created_by=actor.id,
                document_no=document_no,
                batch_no=item.batch_no,
                expiry_date=item.expiry_date,
                allow_negative=negative_ok,
                uom_symbol=line_uom_symbol,
            )
            total += line_total
        total = total.quantize(TWO, rounding=ROUND_HALF_UP)

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
            new_values={"document_no": document_no, "total": str(total), "paid": str(paid)},
        )
        await self.session.commit()
        return self._operation_out(transaction, items=item_rows, total_amount=total, paid_amount=paid, debt=debt)

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
        for line in payload.lines:
            item = items_by_id.get(line.stock_transaction_item_id)
            if item is None:
                raise NotFoundError("Stock In line not found on this document")
            returnable = Decimal(item.quantity) - Decimal(item.returned_quantity)
            if Decimal(line.quantity) > returnable:
                raise ValidationError(
                    f"Cannot return more than the returnable quantity ({returnable})",
                    field_errors={"lines": "Return quantity exceeds returnable"},
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
                quantity=_q4(line.quantity),
                unit_cost=Decimal(item.unit_cost).quantize(TWO, rounding=ROUND_HALF_UP),
                line_refund=refund,
            )
            out_rows.append(row)
            self.session.add(row)
            item.returned_quantity = _q4(Decimal(item.returned_quantity) + Decimal(line.quantity))
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
                    product_name=items_by_id[row.stock_transaction_item_id].product_ref.name,
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

            line_total = (abs(difference) * unit_cost).quantize(TWO, rounding=ROUND_HALF_UP)
            row = StockTransactionItem(
                    stock_transaction_id=transaction.id,
                    product_id=item.product_id,
                product_ref=product,
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
            balance = await _lock_balance(self.session, item.product_id)
            unit_cost = item.unit_cost if item.unit_cost is not None else balance.average_cost
            line_total = (item.quantity * unit_cost).quantize(TWO, rounding=ROUND_HALF_UP)
            product = products[item.product_id]
            reason = getattr(item, "reason", None)
            row = StockTransactionItem(
                    stock_transaction_id=transaction.id,
                    product_id=item.product_id,
                product_ref=product,
                quantity=item.quantity,
                unit_cost=unit_cost,
                batch_no=item.batch_no,
                expiry_date=getattr(item, "expiry_date", None),
                reason=reason,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
            await apply_stock_movement(
                self.session,
                product_id=item.product_id,
                movement_type=kind,
                quantity_delta=-item.quantity,
                unit_cost=unit_cost,
                reference_type="stock_transaction",
                reference_id=transaction.id,
                created_by=actor.id,
                document_no=document_no,
                batch_no=item.batch_no,
                expiry_date=getattr(item, "expiry_date", None),
                note=reason,
                allow_negative=negative_ok,
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
        factor = Decimal(str(payload.factor_to_base or 1))
        if factor <= 0:
            raise ValidationError("factor_to_base must be greater than zero")
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
                    "name": item.product_ref.name if item.product_ref else None,
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
            debt_created=debt is not None,
            debt_id=debt.id if debt is not None else None,
            items=[
                OperationItemOut(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=item.product_ref.name if item.product_ref else None,
                    sku=item.product_ref.sku if item.product_ref else None,
                    uom_symbol=item.uom_symbol,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    system_quantity=item.system_quantity,
                    actual_quantity=item.actual_quantity,
                    batch_no=item.batch_no,
                    expiry_date=item.expiry_date,
                    reason=item.reason,
                    line_total=item.line_total,
                )
                for item in items
            ],
        )

    # ------------------------------------------------------------------ reads

    async def list_movements(self, *, q, product_id, movement_type, start, end, page, limit):
        from app.shared.pagination.params import parse_date_range

        stmt = select(StockMovement)
        count_stmt = select(func.count()).select_from(StockMovement)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(StockMovement.document_no.ilike(pattern))
            count_stmt = count_stmt.where(StockMovement.document_no.ilike(pattern))
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
            count_stmt = count_stmt.where(StockMovement.product_id == product_id)
        if movement_type:
            stmt = stmt.where(StockMovement.movement_type == movement_type)
            count_stmt = count_stmt.where(StockMovement.movement_type == movement_type)
        start_at, end_at = parse_date_range(start, end)
        if start_at is not None:
            stmt = stmt.where(StockMovement.created_at >= start_at)
            count_stmt = count_stmt.where(StockMovement.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(StockMovement.created_at <= end_at)
            count_stmt = count_stmt.where(StockMovement.created_at <= end_at)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(StockMovement.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), int(total)


def movement_to_out(movement: StockMovement) -> MovementOut:
    return MovementOut(
        id=movement.id,
        product_id=movement.product_id,
        product_name=movement.product_ref.name if movement.product_ref else None,
        movement_type=movement.movement_type,
        quantity_delta=movement.quantity_delta,
        unit_cost=movement.unit_cost,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        document_no=movement.document_no,
        batch_no=movement.batch_no,
        expiry_date=movement.expiry_date,
        uom_symbol=movement.uom_symbol,
        note=movement.note,
        created_at=movement.created_at,
    )


async def list_stock_in_transactions_for_supplier(session: AsyncSession, supplier_id, page: int, limit: int):
    """Public interface: supplier purchase/stock-in history."""
    stmt = (
        select(StockTransaction)
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
    return [
        {
            "id": str(t.id),
            "document_no": t.document_no,
            "transaction_date": t.transaction_date.isoformat(),
            "reference_no": t.reference_no,
            "note": t.note,
            "status": t.status,
            "total": str(sum((item.line_total for item in t.items), Decimal("0")).quantize(TWO)),
        }
        for t in rows.scalars().all()
    ], int(total)
