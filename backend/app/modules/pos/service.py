"""POS service: product search, atomic sale completion, returns.

The sale transaction commits sale, items, payment/customer debt, stock
movements, balances, invoice sequence, and audit together — or not at all.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import user_has_permission
from app.modules.auth.models import User
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.pos.models import Sale, SaleItem, SaleReturn, SaleReturnItem, Payment
from app.modules.pos.schemas import (
    POSProductOut,
    SaleItemOut,
    SaleOut,
    SaleReturnItemOut,
    SaleReturnOut,
    UomConversionOut,
)
from app.modules.stock.models import Product
from app.modules.stock.repository import ProductRepository
from app.modules.stock.service import (
    _lock_balance,
    allow_negative_stock,
    apply_stock_movement,
    resolve_outbound_unit_cost,
)
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number

logger = logging.getLogger("stock_pos.pos")


TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


def _q2(value) -> Decimal:
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def _q4(value) -> Decimal:
    return Decimal(value).quantize(FOUR, rounding=ROUND_HALF_UP)


def _to_sale_currency(usd_price, exchange_rate) -> Decimal:
    """Active-version prices are USD; the POS line is priced in the sale
    currency (KHR documents convert by the sale exchange rate)."""
    return (Decimal(usd_price) * Decimal(exchange_rate or 1)).quantize(TWO, rounding=ROUND_HALF_UP)


def _uom_price_from_map(product: Product, uom_id, price_map: dict) -> Decimal | None:
    """USD price of a line's UOM from a {uom_id: price} active-version map,
    mirroring the cart fallbacks (map → conversion row → product base price)."""
    key = str(uom_id or product.uom_id)
    if key in price_map:
        return Decimal(price_map[key])
    for row in (product.uom_conversions or []):
        if str(row.get("uom_id")) == key and row.get("sale_price") is not None:
            return Decimal(str(row["sale_price"]))
    if key == str(product.uom_id) and product.selling_price is not None:
        return Decimal(product.selling_price)
    return None



async def get_walk_in_customer(session: AsyncSession) -> Customer | None:
    result = await session.execute(select(Customer).where(Customer.is_walk_in.is_(True)))
    return result.scalar_one_or_none()


def sale_to_out(
    sale: Sale,
    customer_name: str | None = None,
    change_amount: Decimal = Decimal("0"),
    items: list[SaleItem] | None = None,
) -> SaleOut:
    resolved_items = items if items is not None else list(sale.items)
    return SaleOut(
        id=sale.id,
        invoice_no=sale.invoice_no,
        customer_id=sale.customer_id,
        customer_name=customer_name,
        sale_date=sale.sale_date,
        subtotal=sale.subtotal,
        discount_amount=sale.discount_amount,
        delivery_price=getattr(sale, "delivery_price", Decimal("0")),
        deliveryPrice=getattr(sale, "delivery_price", Decimal("0")),
        grand_total=sale.grand_total,
        paid_amount=sale.paid_amount,
        debt_amount=sale.debt_amount,
        payment_status=sale.payment_status,
        sale_status=sale.sale_status,
        cashier_id=sale.cashier_id,
        note=sale.note,
        change_amount=change_amount,
        currency=getattr(sale, "currency", "USD"),
        exchange_rate=getattr(sale, "exchange_rate", Decimal("1")),
        items=[SaleItemOut.model_validate(item) for item in resolved_items],
    )


class POSService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)

    # ---------------------------------------------------------------- search

    async def search_products(self, *, q: str | None, category_id: uuid.UUID | None, limit: int) -> list[POSProductOut]:
        stmt = (
            select(Product)
            .where(Product.status == "ACTIVE")
            .order_by(Product.name)
            .limit(max(1, min(limit, 50)))
        )
        if q:
            needle = q.strip()
            # Barcode is the operational identifier: an exact (indexed) match
            # wins before name/sku fuzzy search.
            exact = await self.products.get_by_barcode(needle)
            if exact is not None and exact.status == "ACTIVE":
                rows = [exact]
            else:
                pattern = f"%{needle}%"
                stmt = stmt.where(
                    Product.name.ilike(pattern) | Product.sku.ilike(pattern) | Product.barcode.ilike(pattern)
                )
                rows = list((await self.session.execute(stmt)).scalars().all())
            return [await self._product_out(p) for p in rows]
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        rows = await self.session.execute(stmt)
        return [await self._product_out(p) for p in rows.scalars().all()]

    async def product_by_barcode(self, barcode: str) -> POSProductOut:
        product = await self.products.get_by_barcode(barcode.strip())
        if product is None or product.status != "ACTIVE":
            raise NotFoundError("No active product matches this barcode")
        return await self._product_out(product)

    async def _product_out(self, product: Product) -> POSProductOut:
        from app.modules.image.service import resolve_media_url
        from app.modules.stock import sale_prices as sale_price_service

        balance = product.balance
        # Active version prices (batch-specific first, else general) picked
        # per UOM — POS always prices through the active price version.
        version_prices = await sale_price_service.active_version_uom_prices(self.session, product.id)
        # Pricing rows (spec §2.1.3): every row is POS-selectable; the base UOM
        # row is synthesized for legacy products saved without one.
        conversions: list[UomConversionOut] = [
            {
                "uom_id": row["uom_id"],
                "uom_symbol": row.get("uom_symbol") or None,
                "convert_uom_id": uuid.UUID(str(row["convert_uom_id"])) if row.get("convert_uom_id") else None,
                "convert_uom_symbol": row.get("convert_uom_symbol") or None,
                "factor_to_base": Decimal(str(row.get("factor_to_base", 1))),
                "cost_price": Decimal(str(row["cost_price"])) if row.get("cost_price") else None,
                "sale_price": (
                    version_prices.get(str(row["uom_id"]), Decimal(str(row["sale_price"])))
                    if row.get("sale_price") else None
                ),
                "is_default_sale": bool(row.get("is_default_sale")),
            }
            for row in (product.uom_conversions or [])
            if row.get("uom_id")
        ]
        if not any(str(item["uom_id"]) == str(product.uom_id) for item in conversions):
            conversions.insert(
                0,
                {
                    "uom_id": product.uom_id,
                    "uom_symbol": product.uom_ref.symbol if product.uom_ref else None,
                    "convert_uom_id": product.uom_id,
                    "convert_uom_symbol": product.uom_ref.symbol if product.uom_ref else None,
                    "factor_to_base": Decimal("1"),
                    "cost_price": product.cost_price,
                    # selling_price IS the POS-active sale-price version.
                    "sale_price": product.selling_price,
                    "is_default_sale": not any(item["is_default_sale"] for item in conversions),
                },
            )
        return POSProductOut(
            id=product.id,
            sku=product.sku,
            barcode=product.barcode,
            name=product.name,
            category_id=product.category_id,
            category_name=product.category_ref.name if product.category_ref else None,
            selling_price=product.selling_price,
            quantity=balance.quantity if balance else Decimal("0"),
            image_object_key=product.image_object_key,
            image_url=resolve_media_url(product.image_object_key),
            uom_id=product.uom_id,
            uom_symbol=product.uom_ref.symbol if product.uom_ref else None,
            uom_conversions=conversions,
            status=product.status,
        )

    # ------------------------------------------------------------------ sale

    async def complete_sale(self, payload, *, actor: User) -> SaleOut:
        discount_allowed = user_has_permission(actor, "pos.discount")
        if (
            any(item.discount_amount > 0 or item.discount_percent > 0 for item in payload.items)
            or (payload.discount or Decimal("0")) > 0
        ) and not discount_allowed:
            raise ConflictError("You do not have permission to apply discounts")

        customer = await self._resolve_customer(payload)
        products: dict[uuid.UUID, Product] = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in cart", field_errors={"items": "Duplicate product"})
            product = await self.products.get(item.product_id)
            if product is None:
                raise NotFoundError("Product not found")
            if product.status != "ACTIVE":
                raise ValidationError("Inactive products cannot be sold", field_errors={"items": "Product inactive"})
            products[item.product_id] = product

        max_discount = await self._maximum_discount_percent()

        negative_ok = await allow_negative_stock(self.session)
        invoice_no = await allocate_document_number(self.session, "INVOICE")

        sale = Sale(
            invoice_no=invoice_no,
            customer_id=customer.id,
            sale_date=payload.sale_date or datetime.now(timezone.utc),
            cashier_id=actor.id,
            note=payload.note,
            delivery_price=_q2(payload.delivery_price),
            subtotal=Decimal("0.00"),
            grand_total=Decimal("0.00"),
            payment_status="UNPAID",
            currency=payload.currency,
            exchange_rate=payload.exchange_rate,
        )
        self.session.add(sale)
        await self.session.flush()

        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        item_rows: list[SaleItem] = []
        version_prices: dict[uuid.UUID, dict[str, Decimal]] = {}
        general_version_prices: dict[uuid.UUID, dict[str, Decimal]] = {}
        for item in payload.items:
            product = products[item.product_id]
            quantity = item.quantity

            # Active price-version prices per UOM. Batch-first priority:
            # the sold (FEFO) lot's active version wins per UOM, then the
            # general active version, then the product fallbacks.
            if item.product_id not in version_prices:
                from app.modules.stock import batch_service, sale_prices as sale_price_service

                general_prices = await sale_price_service.active_version_uom_prices(
                    self.session, item.product_id
                )
                batch_prices: dict = {}
                if product.track_batch:
                    lots = await batch_service.lock_batches_for_product(self.session, product.id)
                    fefo_batch = lots[0].batch_no if lots else None
                    if fefo_batch:
                        batch_prices = await sale_price_service.active_version_uom_prices(
                            self.session, item.product_id, batch_no=fefo_batch
                        )
                general_version_prices[item.product_id] = general_prices
                version_prices[item.product_id] = {**general_prices, **batch_prices}
            active_uom_prices = version_prices[item.product_id]
            general_uom_prices = general_version_prices[item.product_id]

            # ---- line UOM resolution (stock is always mutated in base UOM) ----
            factor = item.factor_to_base
            uom_id = item.uom_id
            uom_symbol = item.uom_symbol
            uom_code = None
            default_price = active_uom_prices.get(str(product.uom_id), product.selling_price)
            default_price = default_price if default_price is not None else product.selling_price  # POS-active sale price
            if uom_id is not None and str(uom_id) != str(product.uom_id):
                conversion = next(
                    (
                        row
                        for row in (product.uom_conversions or [])
                        if str(row.get("uom_id")) == str(uom_id)
                    ),
                    None,
                )
                if conversion is None:
                    raise ValidationError(
                        "The selected UOM is not a conversion UOM of this product",
                        field_errors={"items": "Invalid UOM"},
                    )
                factor = Decimal(str(conversion.get("factor_to_base", factor)))
                if str(uom_id) in active_uom_prices:
                    # The chosen UOM's price from the ACTIVE version wins.
                    default_price = active_uom_prices[str(uom_id)]
                elif conversion.get("sale_price") is not None:
                    default_price = Decimal(str(conversion["sale_price"]))
                uom_symbol = uom_symbol or conversion.get("uom_symbol") or None
            elif uom_id is not None and str(uom_id) == str(product.uom_id):
                factor = Decimal("1")
                # The base=base Pricing row's sale price is the base unit price
                # (spec §2.1.3); the active version / selling_price stays the fallback.
                base_row = next(
                    (
                        row
                        for row in (product.uom_conversions or [])
                        if str(row.get("uom_id")) == str(uom_id)
                    ),
                    None,
                )
                if str(uom_id) in active_uom_prices:
                    default_price = active_uom_prices[str(uom_id)]
                elif base_row is not None and base_row.get("sale_price") is not None:
                    default_price = Decimal(str(base_row["sale_price"]))
            if uom_id is None:
                uom_id = product.uom_id
                # The frontend factor is NEVER authoritative: a line without
                # an explicit UOM is always the base UOM (factor 1), whatever
                # factor_to_base the caller sent.
                factor = Decimal("1")
                uom_symbol = uom_symbol or (product.uom_ref.symbol if product.uom_ref else None)
                uom_code = product.uom_ref.code if product.uom_ref else None
            else:
                from app.modules.uoms.models import UOM

                uom_row = await self.session.get(UOM, uom_id)
                uom_code = uom_row.code if uom_row else None
                uom_symbol = uom_symbol or (uom_row.symbol if uom_row else None)
            base_quantity = _q4(quantity * factor)
            if base_quantity <= 0:
                raise ValidationError("Line quantity must be greater than zero", field_errors={"items": "Invalid quantity"})

            if item.unit_price is None:
                # No client price → charge the batch-first active version.
                unit_price = _to_sale_currency(default_price, payload.exchange_rate)
            else:
                unit_price = item.unit_price
                # The POS cart always sends the general active price. When a
                # batch-scoped active version changes that price, charge the
                # batch price — unless the cashier manually overrode the line.
                general_price = _uom_price_from_map(product, uom_id, general_uom_prices)
                resolved_price = _uom_price_from_map(product, uom_id, active_uom_prices)
                if (
                    general_price is not None
                    and resolved_price is not None
                    and Decimal(item.unit_price)
                    == _to_sale_currency(general_price, payload.exchange_rate)
                    and _to_sale_currency(resolved_price, payload.exchange_rate)
                    != _to_sale_currency(general_price, payload.exchange_rate)
                ):
                    unit_price = _to_sale_currency(resolved_price, payload.exchange_rate)
            gross = (quantity * unit_price).quantize(TWO, rounding=ROUND_HALF_UP)
            if item.discount_percent > 0:
                discount = _q2(gross * item.discount_percent / Decimal("100"))
            else:
                discount = _q2(item.discount_amount)

            if discount > 0:
                if max_discount > 0:
                    implied_percent = (discount / gross * Decimal("100")) if gross > 0 else Decimal("100")
                    if item.discount_percent > max_discount or implied_percent > max_discount:
                        raise ValidationError(
                            f"Line discount exceeds the maximum allowed ({max_discount}%)",
                            field_errors={"items": "Discount exceeds maximum"},
                        )
                if discount >= gross:
                    raise ValidationError("Discount cannot exceed the line amount", field_errors={"items": "Invalid discount"})

            line_total = gross - discount
            # FEFO batch allocation runs BEFORE the movement is appended so
            # the immutable SALE movement carries the blended cost snapshot
            # (unit_cost 0 on the ledger would make the Stock Out dialog
            # meaningless). The customer price is INDEPENDENT of batch cost.
            from app.modules.stock import batch_service

            provisional = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                uom_id=uom_id,
                uom_code=uom_code,
                uom_symbol=uom_symbol,
                factor_to_base=factor,
                discount_percent=item.discount_percent,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=Decimal("0.00"),
                discount_amount=discount,
                line_total=line_total,
            )
            self.session.add(provisional)
            await self.session.flush()
            # Line cost follows the product's costing option (FIFO lots or
            # weighted average) — the same canonical path as every other
            # outbound. Batch cost only feeds the SaleItemBatch snapshots.
            balance = await _lock_balance(self.session, product.id)
            line_cost = await resolve_outbound_unit_cost(
                self.session, product, base_quantity, fallback=balance.average_cost
            )
            _, consumed_batches = await batch_service.commit_sale_allocations(
                self.session,
                sale_item=provisional,
                product=product,
                quantity_base=base_quantity,
                allow_negative=negative_ok,
            )
            provisional.unit_cost = line_cost
            await self.session.flush()
            # Single-batch lines link the immutable SALE movement to the lot
            # (batch_no / batch_id / expiry click-through); multi-batch lines
            # keep the per-lot detail in the sale_item_batches allocations.
            movement_batch = consumed_batches[0] if len(consumed_batches) == 1 else None
            balance = await apply_stock_movement(
                self.session,
                product_id=product.id,
                movement_type="SALE",
                quantity_delta=-base_quantity,
                unit_cost=line_cost,
                reference_type="sale",
                reference_id=sale.id,
                created_by=actor.id,
                document_no=invoice_no,
                batch_no=movement_batch.batch_no if movement_batch else None,
                batch_id=movement_batch.id if movement_batch else None,
                expiry_date=movement_batch.expiry_date if movement_batch else None,
                allow_negative=negative_ok,
            )
            row = provisional
            item_rows.append(row)
            subtotal += gross
            discount_total += discount

        # Header discount (payload.discount) reduces the sale after line discounts.
        header_discount = _q2(payload.discount)
        if header_discount > 0:
            if max_discount > 0 and subtotal > 0 and (header_discount / subtotal * Decimal("100")) > max_discount:
                raise ValidationError(
                    f"Discount exceeds the maximum allowed ({max_discount}%)",
                    field_errors={"discount": "Discount exceeds maximum"},
                )
            if header_discount >= subtotal - discount_total:
                raise ValidationError("Discount cannot exceed the sale amount", field_errors={"discount": "Invalid discount"})
        discount_total += header_discount

        delivery_price = _q2(payload.delivery_price)
        grand_total = subtotal - discount_total + delivery_price
        sale.subtotal = _q2(subtotal)
        sale.discount_amount = _q2(discount_total)
        sale.grand_total = _q2(grand_total)

        # ---- settle included open debts from `deposit` (separate from sale) ----
        # amount_received / paidAmount applies only to THIS sale's grand_total.
        # deposit is the budget for selected prior-debt payments and never
        # inflates the current sale total or default Paid now.
        remaining_deposit = _q2(payload.deposit)
        for debt_id in payload.included_debt_ids:
            debt_result = await self.session.execute(
                select(CustomerDebt).where(CustomerDebt.id == debt_id).with_for_update()
            )
            debt = debt_result.scalar_one_or_none()
            if debt is None:
                raise NotFoundError("Included customer debt not found")
            if debt.customer_id != customer.id:
                raise ValidationError(
                    "Included debts must belong to the sale's customer",
                    field_errors={"included_debt_ids": "Debt belongs to another customer"},
                )
            if debt.remaining_amount <= 0 or debt.status == "PAID":
                continue
            applied = min(debt.remaining_amount, remaining_deposit)
            if applied > 0:
                debt.paid_amount = debt.paid_amount + applied
                debt.remaining_amount = debt.remaining_amount - applied
                debt.status = "PAID" if debt.remaining_amount == 0 else "PARTIAL"
                await self._create_payment(
                    payment_no=await allocate_document_number(self.session, "CUSTOMER_DEBT_PAYMENT"),
                    sale_id=None,
                    customer_id=customer.id,
                    payment_type="CUSTOMER_DEBT_PAYMENT",
                    payment_method=payload.payment_method if payload.payment_method != "CUSTOMER_DEBT" else (payload.deposit_method or "CASH"),
                    amount=applied,
                    reference_no=sale.invoice_no,
                    actor=actor,
                    customer_debt_id=debt.id,
                )
                await record_audit(
                    self.session,
                    action="customer_debt_payment",
                    module="customers",
                    user_id=actor.id,
                    entity_type="customer_debt",
                    entity_id=debt.id,
                    new_values={
                        "invoice_no": debt.invoice_no,
                        "applied": str(applied),
                        "remaining": str(debt.remaining_amount),
                        "via_sale": sale.invoice_no,
                    },
                )
                remaining_deposit -= applied

        paid_for_sale = max(Decimal("0.00"), min(_q2(payload.amount_received), sale.grand_total))
        debt_amount = sale.grand_total - paid_for_sale

        debt: CustomerDebt | None = None
        change_amount = Decimal("0.00")
        if debt_amount > 0 and customer.is_walk_in:
            raise ValidationError(
                "The walk-in customer cannot make a debt purchase",
                field_errors={"customer_id": "Select a registered customer"},
            )
        if debt_amount > 0:
            debt = CustomerDebt(
                customer_id=customer.id,
                sale_id=sale.id,
                invoice_no=sale.invoice_no,
                original_amount=sale.grand_total,
                paid_amount=paid_for_sale,
                remaining_amount=debt_amount,
                due_date=payload.due_date,
                status="UNPAID" if paid_for_sale == 0 else "PARTIAL",
                currency=sale.currency,
                exchange_rate=sale.exchange_rate,
            )
            self.session.add(debt)
            await self.session.flush()

        sale.paid_amount = paid_for_sale
        sale.debt_amount = debt_amount
        sale.payment_status = "PAID" if debt_amount == 0 else ("PARTIAL" if paid_for_sale > 0 else "UNPAID")

        if paid_for_sale > 0:
            await self._create_payment(
                payment_no=await allocate_document_number(self.session, "CUSTOMER_DEBT_PAYMENT"),
                sale_id=sale.id,
                customer_id=customer.id,
                payment_type="SALE_PAYMENT",
                payment_method=payload.payment_method
                if payload.payment_method != "CUSTOMER_DEBT"
                else (payload.deposit_method or "CASH"),
                amount=paid_for_sale,
                reference_no=payload.reference_no,
                actor=actor,
                customer_debt_id=debt.id if debt else None,
            )
        if payload.payment_method in ("CASH", "BANK_QR"):
            change_amount = _q2(max(Decimal("0.00"), payload.amount_received - sale.grand_total))

        await record_audit(
            self.session,
            action="sale",
            module="pos",
            user_id=actor.id,
            entity_type="sale",
            entity_id=sale.id,
            new_values={
                "invoice_no": invoice_no,
                "grand_total": str(sale.grand_total),
                "payment_method": payload.payment_method,
            },
        )
        await self.session.commit()

        # Telegram sale notification strictly AFTER commit: a notification
        # failure must never roll back the committed sale. Debt sales notify
        # through customer debt payments instead (spec §3.6.2).
        if payload.payment_method in ("CASH", "BANK_QR"):
            from app.shared.telegram.service import notify_sale

            await notify_sale(
                self.session,
                invoice_no=sale.invoice_no,
                occurred_at=sale.sale_date,
                customer=customer.name,
                currency=sale.currency,
                exchange_rate=sale.exchange_rate,
                subtotal=sale.subtotal,
                discount=sale.discount_amount,
                delivery_price=sale.delivery_price,
                total=sale.grand_total,
                paid=sale.paid_amount,
                payment_method=payload.payment_method,
                debt=sale.debt_amount,
                cashier=actor.full_name,
                item_count=len(item_rows),
                customer_phone=getattr(customer, "phone", None),
                items=[
                    {
                        "name": item.product_name,
                        "quantity": str(item.quantity),
                        "uom": item.uom_symbol or "",
                        "unit_price": str(item.unit_price),
                        "line_total": str(item.line_total),
                    }
                    for item in item_rows
                ],
            )
        return sale_to_out(sale, customer_name=customer.name, change_amount=change_amount, items=item_rows)

    async def update_sale(self, sale_id, payload, *, actor: User) -> SaleOut:
        """Edit a completed sale: reverse the original stock (append-only
        compensating movements) then re-apply the new lines, quantities,
        prices and discounts. The customer and immutable payments are kept;
        the outstanding customer debt is recalculated from the new total."""
        discount_allowed = user_has_permission(actor, "pos.discount")
        if (
            any(item.discount_amount > 0 or item.discount_percent > 0 for item in payload.items)
            or (payload.discount or Decimal("0")) > 0
        ) and not discount_allowed:
            raise ConflictError("You do not have permission to apply discounts")

        result = await self.session.execute(
            select(Sale).where(Sale.id == sale_id).with_for_update()
        )
        sale = result.scalar_one_or_none()
        if sale is None:
            raise NotFoundError("Sale not found")
        if sale.sale_status != "COMPLETED":
            raise ConflictError("Only completed sales can be edited")
        existing_items = list(sale.items)
        if any(Decimal(item.returned_quantity or 0) > 0 for item in existing_items):
            raise ConflictError("Sales with returns cannot be edited")
        # Delivery-note items RESTRICT-reference sale_items, so deleting the
        # old lines would raise a FK violation (500). Reject the edit cleanly.
        from app.modules.delivery.models import DeliveryNoteItem

        attached = await self.session.execute(
            select(func.count())
            .select_from(DeliveryNoteItem)
            .where(DeliveryNoteItem.sale_item_id.in_([item.id for item in existing_items]))
        )
        if int(attached.scalar_one() or 0) > 0:
            raise ConflictError("Sales with delivery notes cannot be edited")

        customer = await self.session.get(Customer, sale.customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")

        products: dict[uuid.UUID, Product] = {}
        for item in payload.items:
            if item.product_id in products:
                raise ValidationError("Duplicate product in cart", field_errors={"items": "Duplicate product"})
            product = await self.products.get(item.product_id)
            if product is None:
                raise NotFoundError("Product not found")
            if product.status != "ACTIVE":
                raise ValidationError("Inactive products cannot be sold", field_errors={"items": "Product inactive"})
            products[item.product_id] = product

        max_discount = await self._maximum_discount_percent()
        negative_ok = await allow_negative_stock(self.session)

        from app.modules.stock import batch_service

        # 1) Reverse the original lines: restore their batches and append
        #    compensating SALE_RETURN movements (the old SALE rows are never
        #    mutated), then drop the old items so the new set can be applied.
        for row in existing_items:
            base_quantity = _q4(row.quantity * row.factor_to_base)
            if base_quantity <= 0:
                continue
            await batch_service.restore_sale_batches(
                self.session, sale_item=row, quantity_base=base_quantity
            )
            await apply_stock_movement(
                self.session,
                product_id=row.product_id,
                movement_type="SALE_RETURN",
                quantity_delta=base_quantity,
                unit_cost=row.unit_cost,
                reference_type="sale",
                reference_id=sale.id,
                created_by=actor.id,
                document_no=sale.invoice_no,
                allow_negative=True,
            )
            await self.session.delete(row)
        await self.session.flush()

        # 2) Apply the new lines with the same rules as complete_sale.
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        item_rows: list[SaleItem] = []
        version_prices: dict[uuid.UUID, dict[str, Decimal]] = {}
        general_version_prices: dict[uuid.UUID, dict[str, Decimal]] = {}
        for item in payload.items:
            product = products[item.product_id]
            quantity = item.quantity

            if item.product_id not in version_prices:
                from app.modules.stock import batch_service, sale_prices as sale_price_service

                general_prices = await sale_price_service.active_version_uom_prices(
                    self.session, item.product_id
                )
                batch_prices: dict = {}
                if product.track_batch:
                    lots = await batch_service.lock_batches_for_product(self.session, product.id)
                    fefo_batch = lots[0].batch_no if lots else None
                    if fefo_batch:
                        batch_prices = await sale_price_service.active_version_uom_prices(
                            self.session, item.product_id, batch_no=fefo_batch
                        )
                general_version_prices[item.product_id] = general_prices
                version_prices[item.product_id] = {**general_prices, **batch_prices}
            active_uom_prices = version_prices[item.product_id]
            general_uom_prices = general_version_prices[item.product_id]

            factor = item.factor_to_base
            uom_id = item.uom_id
            uom_symbol = item.uom_symbol
            uom_code = None
            default_price = active_uom_prices.get(str(product.uom_id), product.selling_price)
            default_price = default_price if default_price is not None else product.selling_price
            if uom_id is not None and str(uom_id) != str(product.uom_id):
                conversion = next(
                    (row for row in (product.uom_conversions or []) if str(row.get("uom_id")) == str(uom_id)),
                    None,
                )
                if conversion is None:
                    raise ValidationError(
                        "The selected UOM is not a conversion UOM of this product",
                        field_errors={"items": "Invalid UOM"},
                    )
                factor = Decimal(str(conversion.get("factor_to_base", factor)))
                if str(uom_id) in active_uom_prices:
                    default_price = active_uom_prices[str(uom_id)]
                elif conversion.get("sale_price") is not None:
                    default_price = Decimal(str(conversion["sale_price"]))
                uom_symbol = uom_symbol or conversion.get("uom_symbol") or None
            elif uom_id is not None and str(uom_id) == str(product.uom_id):
                factor = Decimal("1")
                base_row = next(
                    (row for row in (product.uom_conversions or []) if str(row.get("uom_id")) == str(uom_id)),
                    None,
                )
                if str(uom_id) in active_uom_prices:
                    default_price = active_uom_prices[str(uom_id)]
                elif base_row is not None and base_row.get("sale_price") is not None:
                    default_price = Decimal(str(base_row["sale_price"]))
            if uom_id is None:
                uom_id = product.uom_id
                factor = Decimal("1")
                uom_symbol = uom_symbol or (product.uom_ref.symbol if product.uom_ref else None)
                uom_code = product.uom_ref.code if product.uom_ref else None
            else:
                from app.modules.uoms.models import UOM

                uom_row = await self.session.get(UOM, uom_id)
                uom_code = uom_row.code if uom_row else None
                uom_symbol = uom_symbol or (uom_row.symbol if uom_row else None)
            base_quantity = _q4(quantity * factor)
            if base_quantity <= 0:
                raise ValidationError("Line quantity must be greater than zero", field_errors={"items": "Invalid quantity"})

            if item.unit_price is None:
                # No client price → charge the batch-first active version.
                unit_price = _to_sale_currency(default_price, payload.exchange_rate)
            else:
                unit_price = item.unit_price
                # The POS cart always sends the general active price. When a
                # batch-scoped active version changes that price, charge the
                # batch price — unless the cashier manually overrode the line.
                general_price = _uom_price_from_map(product, uom_id, general_uom_prices)
                resolved_price = _uom_price_from_map(product, uom_id, active_uom_prices)
                if (
                    general_price is not None
                    and resolved_price is not None
                    and Decimal(item.unit_price)
                    == _to_sale_currency(general_price, payload.exchange_rate)
                    and _to_sale_currency(resolved_price, payload.exchange_rate)
                    != _to_sale_currency(general_price, payload.exchange_rate)
                ):
                    unit_price = _to_sale_currency(resolved_price, payload.exchange_rate)
            gross = (quantity * unit_price).quantize(TWO, rounding=ROUND_HALF_UP)
            if item.discount_percent > 0:
                discount = _q2(gross * item.discount_percent / Decimal("100"))
            else:
                discount = _q2(item.discount_amount)
            if discount > 0:
                if max_discount > 0:
                    implied_percent = (discount / gross * Decimal("100")) if gross > 0 else Decimal("100")
                    if item.discount_percent > max_discount or implied_percent > max_discount:
                        raise ValidationError(
                            f"Line discount exceeds the maximum allowed ({max_discount}%)",
                            field_errors={"items": "Discount exceeds maximum"},
                        )
                if discount >= gross:
                    raise ValidationError("Discount cannot exceed the line amount", field_errors={"items": "Invalid discount"})
            line_total = gross - discount

            provisional = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                uom_id=uom_id,
                uom_code=uom_code,
                uom_symbol=uom_symbol,
                factor_to_base=factor,
                discount_percent=item.discount_percent,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=Decimal("0.00"),
                discount_amount=discount,
                line_total=line_total,
            )
            self.session.add(provisional)
            await self.session.flush()
            balance = await _lock_balance(self.session, product.id)
            line_cost = await resolve_outbound_unit_cost(
                self.session, product, base_quantity, fallback=balance.average_cost
            )
            _, consumed_batches = await batch_service.commit_sale_allocations(
                self.session,
                sale_item=provisional,
                product=product,
                quantity_base=base_quantity,
                allow_negative=negative_ok,
            )
            provisional.unit_cost = line_cost
            await self.session.flush()
            movement_batch = consumed_batches[0] if len(consumed_batches) == 1 else None
            await apply_stock_movement(
                self.session,
                product_id=product.id,
                movement_type="SALE",
                quantity_delta=-base_quantity,
                unit_cost=line_cost,
                reference_type="sale",
                reference_id=sale.id,
                created_by=actor.id,
                document_no=sale.invoice_no,
                batch_no=movement_batch.batch_no if movement_batch else None,
                batch_id=movement_batch.id if movement_batch else None,
                expiry_date=movement_batch.expiry_date if movement_batch else None,
                allow_negative=negative_ok,
            )
            item_rows.append(provisional)
            subtotal += gross
            discount_total += discount

        header_discount = _q2(payload.discount)
        if header_discount > 0:
            if max_discount > 0 and subtotal > 0 and (header_discount / subtotal * Decimal("100")) > max_discount:
                raise ValidationError(
                    f"Discount exceeds the maximum allowed ({max_discount}%)",
                    field_errors={"discount": "Discount exceeds maximum"},
                )
            if header_discount >= subtotal - discount_total:
                raise ValidationError("Discount cannot exceed the sale amount", field_errors={"discount": "Invalid discount"})
        discount_total += header_discount
        delivery_price = _q2(payload.delivery_price)
        grand_total = subtotal - discount_total + delivery_price

        sale.sale_date = payload.sale_date or sale.sale_date
        sale.note = payload.note
        sale.currency = payload.currency
        sale.exchange_rate = payload.exchange_rate
        sale.subtotal = _q2(subtotal)
        sale.discount_amount = _q2(discount_total)
        sale.delivery_price = delivery_price
        sale.grand_total = _q2(grand_total)

        # 3) Recalculate the outstanding customer debt from the new total.
        #    Recorded payments are immutable, so the already-paid amount stands.
        debt_result = await self.session.execute(
            select(CustomerDebt).where(CustomerDebt.sale_id == sale.id).with_for_update()
        )
        debt = debt_result.scalars().first()
        existing_paid = _q2(debt.paid_amount) if debt is not None else _q2(sale.paid_amount)
        paid_for_sale = max(Decimal("0.00"), min(existing_paid, sale.grand_total))
        debt_amount = sale.grand_total - paid_for_sale
        if debt_amount > 0 and customer.is_walk_in:
            raise ValidationError(
                "The walk-in customer cannot make a debt purchase",
                field_errors={"customer_id": "Select a registered customer"},
            )
        if debt is not None:
            debt.original_amount = sale.grand_total
            debt.paid_amount = paid_for_sale
            debt.remaining_amount = debt_amount
            debt.status = "PAID" if debt_amount == 0 else ("PARTIAL" if paid_for_sale > 0 else "UNPAID")
            # The edit rewrites the sale currency/rate; the debt must follow so
            # amounts and their normalization stay in one currency.
            debt.currency = sale.currency
            debt.exchange_rate = sale.exchange_rate
        elif debt_amount > 0:
            self.session.add(
                CustomerDebt(
                    customer_id=customer.id,
                    sale_id=sale.id,
                    invoice_no=sale.invoice_no,
                    original_amount=sale.grand_total,
                    paid_amount=paid_for_sale,
                    remaining_amount=debt_amount,
                    due_date=getattr(payload, "due_date", None),
                    status="UNPAID" if paid_for_sale == 0 else "PARTIAL",
                    currency=sale.currency,
                    exchange_rate=sale.exchange_rate,
                )
            )
        sale.paid_amount = paid_for_sale
        sale.debt_amount = debt_amount
        sale.payment_status = "PAID" if debt_amount == 0 else ("PARTIAL" if paid_for_sale > 0 else "UNPAID")

        await record_audit(
            self.session,
            action="sale_update",
            module="pos",
            user_id=actor.id,
            entity_type="sale",
            entity_id=sale.id,
            new_values={"invoice_no": sale.invoice_no, "grand_total": str(sale.grand_total)},
        )
        await self.session.commit()
        return sale_to_out(sale, customer_name=customer.name, items=item_rows)

    async def _resolve_customer(self, payload) -> Customer:
        if payload.customer_id is None:
            walk_in = await get_walk_in_customer(self.session)
            if walk_in is None:
                raise ValidationError("Walk-in customer is not seeded", field_errors={"customer_id": "Missing walk-in customer"})
            return walk_in
        customer = await self.session.get(Customer, payload.customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def _maximum_discount_percent(self) -> Decimal:
        from app.modules.administration import get_setting_value

        value = await get_setting_value(self.session, "pos", "maximum_discount", 0)
        try:
            return Decimal(str(value or 0))
        except Exception:
            return Decimal("0")

    async def _create_payment(
        self,
        *,
        payment_no,
        sale_id,
        customer_id,
        payment_type,
        payment_method,
        amount,
        reference_no,
        actor,
        customer_debt_id=None,
    ) -> Payment:
        payment = Payment(
            payment_no=payment_no,
            sale_id=sale_id,
            customer_id=customer_id,
            customer_debt_id=customer_debt_id,
            payment_type=payment_type,
            payment_method=payment_method,
            amount=_q2(amount),
            reference_no=reference_no,
            created_by=actor.id,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    # --------------------------------------------------------------- receipt

    async def build_receipt(self, sale: Sale) -> dict:
        """Print-ready bilingual invoice payload (the frontend renders HTML)."""
        from zoneinfo import ZoneInfo

        from app.modules.administration import get_setting_value

        shop_name = await get_setting_value(self.session, "shop", "shop_name", "Yoeun Sokhon Pharmacy")
        shop_address = await get_setting_value(self.session, "shop", "address", "")
        shop_phone = await get_setting_value(self.session, "shop", "phone", "")
        logo = await get_setting_value(self.session, "invoice", "logo", "")
        tz_name = await get_setting_value(self.session, "system", "timezone", "UTC")
        try:
            tz = ZoneInfo(str(tz_name) or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")
        # Invoice presentation settings (paper size, exchange-rate display,
        # footer fallback) — the frontend reads these to render the paper.
        paper_size = await get_setting_value(self.session, "invoice", "paper_size", "A4")
        show_exchange_rate = bool(
            await get_setting_value(self.session, "invoice", "show_exchange_rate", False)
        )
        footer = await get_setting_value(self.session, "invoice", "footer", "")
        receipt_footer = await get_setting_value(self.session, "pos", "receipt_footer", "")
        receipt_footer = footer or receipt_footer
        sale_date = sale.sale_date if sale.sale_date.tzinfo else sale.sale_date.replace(tzinfo=timezone.utc)

        cashier = None
        customer_name = None
        cashier_result = await self.session.execute(
            select(User.full_name).where(User.id == sale.cashier_id)
        )
        cashier = cashier_result.scalar_one_or_none()
        customer_result = await self.session.execute(
            select(Customer.name, Customer.phone, Customer.address).where(Customer.id == sale.customer_id)
        )
        customer_row = customer_result.one_or_none()
        customer_name = customer_row.name if customer_row else None
        customer_phone = customer_row.phone if customer_row else None
        customer_address = customer_row.address if customer_row else None

        debt_result = await self.session.execute(
            select(func.coalesce(func.sum(CustomerDebt.remaining_amount), 0)).where(
                CustomerDebt.sale_id == sale.id
            )
        )
        debt_remaining = Decimal(debt_result.scalar_one())

        method_result = await self.session.execute(
            select(Payment.payment_method)
            .where(Payment.sale_id == sale.id, Payment.payment_type == "SALE_PAYMENT")
            .order_by(Payment.created_at.desc(), Payment.id)
            .limit(1)
        )
        payment_method = method_result.scalar_one_or_none() or (
            "CUSTOMER_DEBT" if debt_remaining > 0 else "UNPAID"
        )

        return {
            "shop": {
                "name": shop_name,
                "address": shop_address,
                "phone": shop_phone,
                "logo": logo or None,
            },
            "invoice_no": sale.invoice_no,
            "sale_date": sale_date.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S"),
            "cashier": cashier,
            "customer": customer_name,
            # Customer contact snapshot (only when the customer has one).
            "customer_phone": customer_phone or None,
            "customerPhone": customer_phone or None,
            "customer_address": customer_address or None,
            "customerAddress": customer_address or None,
            # Document currency: the whole receipt renders in THIS currency.
            "currency": sale.currency,
            "exchange_rate": str(sale.exchange_rate),
            "exchangeRate": str(sale.exchange_rate),
            # Presentation settings (backend values are authoritative).
            "paper_size": paper_size,
            "paperSize": paper_size,
            "show_exchange_rate": show_exchange_rate,
            "showExchangeRate": show_exchange_rate,
            "footer": receipt_footer or None,
            "items": [
                {
                    "id": item.id,
                    "name": item.product_name,
                    "sku": item.sku,
                    "barcode": item.barcode,
                    "uom": item.uom_symbol,
                    "uom_symbol": item.uom_symbol,
                    "quantity": str(item.quantity),
                    "qty": str(item.quantity),
                    "unit_price": str(item.unit_price),
                    "discount": str(item.discount_amount),
                    "discount_percent": str(item.discount_percent),
                    "line_total": str(item.line_total),
                }
                for item in sale.items
            ],
            "subtotal": str(sale.subtotal),
            "discount": str(sale.discount_amount),
            "delivery_price": str(sale.delivery_price),
            "deliveryPrice": str(sale.delivery_price),
            "grand_total": str(sale.grand_total),
            "paid": str(sale.paid_amount),
            "amount_received": str(sale.paid_amount),
            "amountReceived": str(sale.paid_amount),
            "debt": str(sale.debt_amount),
            "change": str(max(Decimal("0"), sale.paid_amount - (sale.grand_total - sale.debt_amount)))
            if sale.debt_amount == 0
            else "0.00",
            "debt_remaining": str(debt_remaining),
            "payment_method": payment_method,
            "payment_status": sale.payment_status,
            "note": sale.note,
            "receipt_ready_for_print": True,
        }

    # ------------------------------------------------------------------ read

    async def get_sale(self, sale_id: uuid.UUID) -> Sale:
        result = await self.session.execute(select(Sale).where(Sale.id == sale_id))
        sale = result.scalar_one_or_none()
        if sale is None:
            raise NotFoundError("Sale not found")
        return sale

    async def get_sale_out(self, sale_id: uuid.UUID) -> SaleOut:
        """GET path detail with the customer name resolved (the SPA edit screen
        shows the buyer without depending on the cached options list)."""
        sale = await self.get_sale(sale_id)
        customer_name: str | None = None
        if sale.customer_id is not None:
            from app.modules.customers.models import Customer

            result = await self.session.execute(
                select(Customer.name).where(Customer.id == sale.customer_id)
            )
            customer_name = result.scalar_one_or_none()
        return sale_to_out(sale, customer_name=customer_name)

    async def list_sales(self, *, q, customer_id, start, end, page, limit):
        from app.shared.pagination.params import parse_date_range

        stmt = select(Sale)
        count_stmt = select(func.count()).select_from(Sale)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Sale.invoice_no.ilike(pattern))
            count_stmt = count_stmt.where(Sale.invoice_no.ilike(pattern))
        if customer_id is not None:
            stmt = stmt.where(Sale.customer_id == customer_id)
            count_stmt = count_stmt.where(Sale.customer_id == customer_id)
        start_at, end_at = parse_date_range(start, end)
        if start_at is not None:
            stmt = stmt.where(Sale.sale_date >= start_at)
            count_stmt = count_stmt.where(Sale.sale_date >= start_at)
        if end_at is not None:
            stmt = stmt.where(Sale.sale_date <= end_at)
            count_stmt = count_stmt.where(Sale.sale_date <= end_at)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Sale.sale_date.desc()).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    # ---------------------------------------------------------------- return

    async def return_sale(self, sale_id: uuid.UUID, payload, *, actor: User) -> SaleReturnOut:
        # Lock the sale row so concurrent returns (and sale edits) serialize;
        # without it two requests could both read the same returned_quantity
        # and over-return stock/refunds.
        result = await self.session.execute(
            select(Sale).where(Sale.id == sale_id).with_for_update()
        )
        sale = result.scalar_one_or_none()
        if sale is None:
            raise NotFoundError("Sale not found")
        if sale.sale_status not in ("COMPLETED", "PARTIAL_RETURN"):
            raise ConflictError("This sale can no longer be returned")

        items_by_id: dict[uuid.UUID, SaleItem] = {item.id: item for item in sale.items}
        # Sum requested quantities per line first: duplicate sale_item_id rows
        # must be validated against the remaining quantity as a whole, never
        # each independently.
        requested: dict[uuid.UUID, Decimal] = {}
        for return_item in payload.items:
            sale_item = items_by_id.get(return_item.sale_item_id)
            if sale_item is None:
                raise NotFoundError("Sale item not found on this sale")
            requested[return_item.sale_item_id] = (
                requested.get(return_item.sale_item_id, Decimal("0")) + return_item.quantity
            )
        for item_id, total_quantity in requested.items():
            sale_item = items_by_id[item_id]
            remaining = sale_item.quantity - sale_item.returned_quantity
            if total_quantity > remaining:
                raise ValidationError(
                    f"Cannot return more than the remaining quantity ({remaining})",
                    field_errors={"items": "Return quantity exceeds remaining"},
                )

        return_no = await allocate_document_number(self.session, "SALE_RETURN")
        sale_return = SaleReturn(
            return_no=return_no,
            sale_id=sale.id,
            return_date=payload.return_date or datetime.now(timezone.utc),
            refund_amount=Decimal("0.00"),
            reason=payload.reason,
            created_by=actor.id,
        )
        self.session.add(sale_return)
        await self.session.flush()

        refund_total = Decimal("0.00")
        out_items: list[SaleReturnItem] = []
        for return_item in payload.items:
            sale_item = items_by_id[return_item.sale_item_id]
            refund = _q2(sale_item.line_total * return_item.quantity / sale_item.quantity)
            row = SaleReturnItem(
                sale_return_id=sale_return.id,
                sale_item_id=sale_item.id,
                product_id=sale_item.product_id,
                product_name=sale_item.product_name,
                quantity=return_item.quantity,
                refund_amount=refund,
                restock=return_item.restock,
            )
            out_items.append(row)
            self.session.add(row)
            sale_item.returned_quantity = sale_item.returned_quantity + return_item.quantity
            if return_item.restock:
                base_return = _q4(Decimal(return_item.quantity) * Decimal(sale_item.factor_to_base))
                # Restore to the ORIGINAL sold batches (newest allocation
                # first) when the sale line carries batch allocations;
                # never an arbitrary batch (spec: sale return).
                from app.modules.stock import batch_service

                await batch_service.restore_sale_batches(
                    self.session,
                    sale_item=sale_item,
                    quantity_base=base_return,
                )
                await apply_stock_movement(
                    self.session,
                    product_id=sale_item.product_id,
                    movement_type="SALE_RETURN",
                    # Stock is always mutated in the base UOM: the sold line
                    # quantity was in the selected Pricing UOM.
                    quantity_delta=base_return,
                    unit_cost=sale_item.unit_cost,
                    reference_type="sale_return",
                    reference_id=sale_return.id,
                    created_by=actor.id,
                    document_no=return_no,
                    note=payload.reason,
                )
            refund_total += refund
        sale_return.refund_amount = _q2(refund_total)

        # A returned sale reduces what the customer still owes.
        debt_result = await self.session.execute(
            select(CustomerDebt).where(CustomerDebt.sale_id == sale.id).with_for_update()
        )
        debt = debt_result.scalar_one_or_none()
        if debt is not None and debt.remaining_amount > 0:
            reduction = min(sale_return.refund_amount, debt.remaining_amount)
            debt.remaining_amount = debt.remaining_amount - reduction
            debt.paid_amount = debt.original_amount - debt.remaining_amount
            debt.status = "PAID" if debt.remaining_amount == 0 else "PARTIAL"

        fully_returned = all(
            item.returned_quantity >= item.quantity for item in sale.items
        )
        sale.sale_status = "RETURNED" if fully_returned else "PARTIAL_RETURN"

        await record_audit(
            self.session,
            action="sale_return",
            module="pos",
            user_id=actor.id,
            entity_type="sale_return",
            entity_id=sale_return.id,
            new_values={
                "return_no": return_no,
                "invoice_no": sale.invoice_no,
                "refund_amount": str(sale_return.refund_amount),
            },
        )
        await self.session.commit()

        return SaleReturnOut(
            id=sale_return.id,
            return_no=sale_return.return_no,
            sale_id=sale.id,
            invoice_no=sale.invoice_no,
            return_date=sale_return.return_date,
            refund_amount=sale_return.refund_amount,
            reason=sale_return.reason,
            items=[
                SaleReturnItemOut(
                    id=row.id,
                    sale_item_id=row.sale_item_id,
                    product_id=row.product_id,
                    product_name=items_by_id[row.sale_item_id].product_name,
                    quantity=row.quantity,
                    refund_amount=row.refund_amount,
                    restock=row.restock,
                )
                for row in out_items
            ],
        )
