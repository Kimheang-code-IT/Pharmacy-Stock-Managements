"""POS service: product search, atomic sale completion, returns.

The sale transaction commits sale, items, payment/customer debt, stock
movements, balances, invoice sequence, and audit together — or not at all.
"""

from __future__ import annotations

import asyncio
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
from app.modules.stock.service import allow_negative_stock, apply_stock_movement
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number

logger = logging.getLogger("stock_pos.pos")


def _schedule_invoice_pdf(sale_id: uuid.UUID) -> None:
    """Best-effort archived-invoice generation after the sale has committed.
    PDF/Telegram failure never rolls the sale back."""

    async def _run() -> None:
        from app.core.database import SessionFactory

        try:
            async with SessionFactory() as session:
                result = await session.execute(select(Sale).where(Sale.id == sale_id))
                sale = result.scalar_one_or_none()
                if sale is None:
                    return
                await POSService(session).get_or_generate_invoice_pdf(sale)
        except Exception:
            logger.warning("Invoice PDF generation skipped for sale %s", sale_id, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_run())

TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


def _q2(value) -> Decimal:
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def _q4(value) -> Decimal:
    return Decimal(value).quantize(FOUR, rounding=ROUND_HALF_UP)


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
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        rows = await self.session.execute(stmt)
        return [self._product_out(p) for p in rows.scalars().all()]

    async def product_by_barcode(self, barcode: str) -> POSProductOut:
        product = await self.products.get_by_barcode(barcode.strip())
        if product is None or product.status != "ACTIVE":
            raise NotFoundError("No active product matches this barcode")
        return self._product_out(product)

    def _product_out(self, product: Product) -> POSProductOut:
        from app.modules.image.service import resolve_media_url

        balance = product.balance
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
                "sale_price": Decimal(str(row["sale_price"])) if row.get("sale_price") else None,
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
        )
        self.session.add(sale)
        await self.session.flush()

        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        item_rows: list[SaleItem] = []
        for item in payload.items:
            product = products[item.product_id]
            quantity = item.quantity

            # ---- line UOM resolution (stock is always mutated in base UOM) ----
            factor = item.factor_to_base
            uom_id = item.uom_id
            uom_symbol = item.uom_symbol
            uom_code = None
            default_price = product.selling_price  # POS-active sale price
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
                if conversion.get("sale_price") is not None:
                    default_price = Decimal(str(conversion["sale_price"]))
                uom_symbol = uom_symbol or conversion.get("uom_symbol") or None
            elif uom_id is not None and str(uom_id) == str(product.uom_id):
                factor = Decimal("1")
                # The base=base Pricing row's sale price is the base unit price
                # (spec §2.1.3); selling_price stays the fallback.
                base_row = next(
                    (
                        row
                        for row in (product.uom_conversions or [])
                        if str(row.get("uom_id")) == str(uom_id)
                    ),
                    None,
                )
                if base_row is not None and base_row.get("sale_price") is not None:
                    default_price = Decimal(str(base_row["sale_price"]))
            if uom_id is None:
                uom_id = product.uom_id
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

            unit_price = item.unit_price if item.unit_price is not None else default_price
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
            balance = await apply_stock_movement(
                self.session,
                product_id=product.id,
                movement_type="SALE",
                quantity_delta=-base_quantity,
                unit_cost=product.cost_price if product.balance is None else product.balance.average_cost,
                reference_type="sale",
                reference_id=sale.id,
                created_by=actor.id,
                document_no=invoice_no,
                allow_negative=negative_ok,
            )
            row = SaleItem(
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
                unit_cost=balance.average_cost,
                discount_amount=discount,
                line_total=line_total,
            )
            item_rows.append(row)
            self.session.add(row)
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

        # ---- settle included open customer debts from the paid amount ----
        settled_total = Decimal("0.00")
        settled_debts: list[tuple[CustomerDebt, Decimal]] = []
        remaining_paid = _q2(payload.amount_received)
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
            applied = min(debt.remaining_amount, remaining_paid)
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
                settled_total += applied
                settled_debts.append((debt, applied))
                remaining_paid -= applied

        paid_for_sale = max(Decimal("0.00"), min(remaining_paid, sale.grand_total))
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
            change_amount = _q2(payload.amount_received - settled_total - sale.grand_total)

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

        await self._queue_payment_notify(sale, customer=customer, request=payload, actor=actor, item_count=len(item_rows))
        _schedule_invoice_pdf(sale.id)
        return sale_to_out(sale, customer_name=customer.name, change_amount=change_amount, items=item_rows)

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

    async def _queue_payment_notify(self, sale, *, customer, request, actor, item_count: int) -> None:
        """Best-effort Telegram invoice text after commit (spec 3.6.2).

        Only fully-tendered cash / Bank-QR sales notify; debt sales surface
        through customer debt payments instead. Never raises: a notification
        problem must not affect the already-committed sale.
        """
        if request.payment_method not in ("CASH", "BANK_QR"):
            return
        try:
            from app.modules.administration import get_setting_value

            enabled = await get_setting_value(
                self.session,
                "telegram",
                "payment_invoice_notify_enabled",
                True,
            )
            if not enabled:
                return
            from app.shared.telegram import queue_payment_invoice_notify

            queue_payment_invoice_notify(
                {
                    "kind": "SALE",
                    "invoice_no": sale.invoice_no,
                    "occurred_at": sale.sale_date.isoformat(),
                    "customer": customer.name,
                    "item_count": item_count,
                    "subtotal": str(sale.subtotal),
                    "discount": str(sale.discount_amount),
                    "total": str(sale.grand_total),
                    "paid": str(sale.paid_amount),
                    "payment_method": request.payment_method,
                    "remaining": str(sale.debt_amount),
                    "cashier": actor.full_name,
                }
            )
        except Exception:
            import logging

            logging.getLogger("stock_pos.pos").warning(
                "Telegram payment notify hook failed for %s", sale.invoice_no, exc_info=True
            )

    # --------------------------------------------------------------- receipt

    async def build_receipt(self, sale: Sale) -> dict:
        """Print-ready bilingual invoice payload (the frontend renders HTML)."""
        from datetime import datetime
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
        sale_date = sale.sale_date if sale.sale_date.tzinfo else sale.sale_date.replace(tzinfo=timezone.utc)

        cashier = None
        customer_name = None
        cashier_result = await self.session.execute(
            select(User.full_name).where(User.id == sale.cashier_id)
        )
        cashier = cashier_result.scalar_one_or_none()
        customer_result = await self.session.execute(
            select(Customer.name).where(Customer.id == sale.customer_id)
        )
        customer_name = customer_result.scalar_one_or_none()

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
            "items": [
                {
                    "id": item.id,
                    "name": item.product_name,
                    "sku": item.sku,
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
            "change": str(max(Decimal("0"), sale.paid_amount - (sale.grand_total - sale.debt_amount)))
            if sale.debt_amount == 0
            else "0.00",
            "debt_remaining": str(debt_remaining),
            "payment_method": payment_method,
            "payment_status": sale.payment_status,
            "note": sale.note,
            "receipt_ready_for_print": True,
        }

    # ------------------------------------------------------------- invoice pdf

    async def get_or_generate_invoice_pdf(self, sale: Sale) -> bytes:
        """Archived invoice PDF: serve the stored object when present, otherwise
        render it from the receipt payload, archive it, and record the key.
        Failure must never affect the sale transaction (this runs after commit
        or on an explicit GET)."""
        from app.modules.pos.invoice_pdf import load_invoice_pdf

        if sale.invoice_pdf_object_key:
            stored = load_invoice_pdf(sale.invoice_pdf_object_key)
            if stored:
                return stored

        receipt = await self.build_receipt(sale)
        from app.modules.pos.invoice_pdf import build_invoice_pdf, save_invoice_pdf

        content = build_invoice_pdf(receipt)
        object_key = f"invoices/{sale.id}.pdf"
        save_invoice_pdf(object_key, content)
        sale.invoice_pdf_object_key = object_key
        await self.session.commit()
        return content

    # ------------------------------------------------------------------ read

    async def get_sale(self, sale_id: uuid.UUID) -> Sale:
        result = await self.session.execute(select(Sale).where(Sale.id == sale_id))
        sale = result.scalar_one_or_none()
        if sale is None:
            raise NotFoundError("Sale not found")
        return sale

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
        sale = await self.get_sale(sale_id)
        if sale.sale_status not in ("COMPLETED", "PARTIAL_RETURN"):
            raise ConflictError("This sale can no longer be returned")

        items_by_id: dict[uuid.UUID, SaleItem] = {item.id: item for item in sale.items}
        for return_item in payload.items:
            sale_item = items_by_id.get(return_item.sale_item_id)
            if sale_item is None:
                raise NotFoundError("Sale item not found on this sale")
            remaining = sale_item.quantity - sale_item.returned_quantity
            if return_item.quantity > remaining:
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
                quantity=return_item.quantity,
                refund_amount=refund,
                restock=return_item.restock,
            )
            out_items.append(row)
            self.session.add(row)
            sale_item.returned_quantity = sale_item.returned_quantity + return_item.quantity
            if return_item.restock:
                await apply_stock_movement(
                    self.session,
                    product_id=sale_item.product_id,
                    movement_type="SALE_RETURN",
                    quantity_delta=return_item.quantity,
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
