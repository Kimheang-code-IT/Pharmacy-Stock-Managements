"""Report aggregation service — spec section 2.1.10 (five approved reports).

All reports are read-only aggregations over the authoritative transaction
tables; every metric must reconcile with the underlying movements/payments.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import DateTime, String, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ConflictError, ValidationError
from app.modules.auth.models import User
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.pos.models import Payment, Sale, SaleItem, SaleItemBatch, SaleReturn, SaleReturnItem
from app.modules.reports.models import Expense
from app.modules.reports.schemas import ExpenseCreate
from app.modules.stock.models import (
    Product,
    PurchaseReturn,
    PurchaseReturnItem,
    StockMovement,
    StockTransaction,
    StockTransactionItem,
)
from app.modules.suppliers.models import Supplier, SupplierDebt
from app.shared.audit.service import record_audit

from app.shared.pagination.params import parse_date_range

Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

# Reporting currency. All documents carry their own currency + exchange-rate
# snapshot ("KHR per 1 USD"); summaries normalize every amount to this currency.
REPORT_CURRENCY = "USD"

# CSV exports are bounded so a single request cannot materialize an unbounded
# row set into memory (P4); the body is also streamed in chunks.
EXPORT_ROW_LIMIT = 20000


def _usd(expression, currency_col, rate_col):
    """Normalize a money expression recorded in a document currency to USD
    (KHR rows divide by the exchange rate applied on the document; USD rows
    pass through). Multi-currency aggregates must never mix raw amounts."""
    return case((currency_col == "KHR", expression / rate_col), else_=expression)


def _day_start(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _range(start: date | str | None, end: date | str | None) -> tuple[datetime, datetime]:
    """Half-open [start, end) UTC window; list params may pass raw strings."""
    if isinstance(start, str):
        parsed, _ = parse_date_range(start, None)
        start = parsed.date() if parsed else None
    if isinstance(end, str):
        _, parsed = parse_date_range(None, end)
        end = parsed.date() if parsed else None
    today = datetime.now(timezone.utc).date()
    end_date = end or today
    start_date = start or (end_date - timedelta(days=29))
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return _day_start(start_date), _day_start(end_date + timedelta(days=1))


class ReportsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------------------------------------------------- sales report

    def _sales_query(self) -> select:
        # Latest customer-debt due date for the sale (one debt row per sale).
        due_date = (
            select(CustomerDebt.due_date)
            .where(CustomerDebt.sale_id == Sale.id)
            .order_by(CustomerDebt.created_at.desc(), CustomerDebt.id)
            .limit(1)
            .correlate(Sale)
            .scalar_subquery()
        )
        # Batch-snapshot COGS for the line (USD, base units): the exact per-lot
        # cost recorded at checkout. NULL for pre-0034 lines — those fall back
        # to the sale item's unit_cost snapshot in `_sales_row`.
        batch_cost_usd = (
            select(func.sum(SaleItemBatch.quantity_base * SaleItemBatch.cost_per_base))
            .where(SaleItemBatch.sale_item_id == SaleItem.id)
            .correlate(SaleItem)
            .scalar_subquery()
        )
        return (
            select(
                Sale.id,
                Sale.sale_date,
                Sale.invoice_no,
                Customer.name.label("customer_name"),
                SaleItem.product_name.label("product_name"),
                SaleItem.id.label("sale_item_id"),
                SaleItem.product_id.label("product_id"),
                SaleItem.quantity,
                SaleItem.unit_price,
                SaleItem.discount_amount,
                SaleItem.line_total,
                SaleItem.returned_quantity,
                SaleItem.unit_cost,
                batch_cost_usd.label("batch_cost_usd"),
                SaleItem.factor_to_base,
                User.full_name.label("cashier_name"),
                Sale.debt_amount,
                # Document currency of the sale — reprints and grouped report
                # rows must use the stored rate, never the shop's current one.
                Sale.currency,
                Sale.exchange_rate,
                # Saved sale header (repeat per line) so the SPA shows the real
                # checkout values instead of recomputing them.
                Sale.subtotal.label("subtotal"),
                Sale.discount_amount.label("sale_discount"),
                Sale.delivery_price.label("delivery_price"),
                Sale.grand_total.label("grand_total"),
                Sale.paid_amount.label("paid_amount"),
                Sale.payment_status.label("payment_status"),
                Sale.note.label("note"),
                due_date.label("due_date"),
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            # Product is only needed for the category filter; a deleted product
            # leaves the line intact via its snapshots.
            .join(Product, Product.id == SaleItem.product_id, isouter=True)
            .join(Customer, Customer.id == Sale.customer_id)
            .join(User, User.id == Sale.cashier_id)
        )

    @staticmethod
    def _sales_row(row, payment_method: str) -> dict:
        quantity = Decimal(row.quantity)
        returned = Decimal(row.returned_quantity)
        line_total = Decimal(row.line_total)
        unit_cost = Decimal(row.unit_cost)
        factor = Decimal(row.factor_to_base or 1)
        net_quantity = quantity - returned
        return_amount = (line_total * returned / quantity).quantize(Q2) if quantity else Q2 * 0
        net_sales = line_total - return_amount
        # COGS prefers the exact per-batch cost snapshot recorded at checkout
        # (sale_item_batches), scaled for partial returns; legacy lines without
        # batch snapshots fall back to the sale-item unit_cost × base quantity.
        batch_cost = getattr(row, "batch_cost_usd", None)
        if batch_cost is not None and quantity:
            cost_usd = (Decimal(batch_cost) * net_quantity / quantity)
        else:
            cost_usd = unit_cost * net_quantity * factor
        cost = (
            (cost_usd * Decimal(row.exchange_rate or 1)).quantize(Q2)
            if str(row.currency or "USD").upper() == "KHR"
            else cost_usd.quantize(Q2)
        )
        return {
            "sale_id": row.id,
            "sale_item_id": row.sale_item_id,
            "product_id": row.product_id,
            "sale_date": row.sale_date,
            "invoice_no": row.invoice_no,
            "customer_name": row.customer_name,
            "product_name": row.product_name,
            "quantity": quantity,
            "returned_quantity": returned,
            "returnable_quantity": (quantity - returned).quantize(Q4),
            "selling_price": Decimal(row.unit_price),
            "discount_amount": Decimal(row.discount_amount),
            "sales_amount": line_total,
            "return_amount": return_amount,
            "net_quantity": net_quantity,
            "cost": cost,
            "gross_profit": (net_sales - cost).quantize(Q2),
            "debt_amount": Decimal(row.debt_amount or 0),
            "cashier_name": row.cashier_name,
            "payment_method": payment_method,
            # Saved sale header — grouped report rows show these directly.
            "subtotal": Decimal(row.subtotal or 0),
            "sale_discount": Decimal(row.sale_discount or 0),
            "delivery_price": Decimal(row.delivery_price or 0),
            "grand_total": Decimal(row.grand_total or 0),
            "paid_amount": Decimal(row.paid_amount or 0),
            "payment_status": row.payment_status,
            "note": row.note,
            "due_date": row.due_date,
            # Document currency snapshot for grouped rows / invoice reprints.
            "currency": row.currency,
            "exchange_rate": row.exchange_rate,
        }

    async def _payment_methods(self, sale_ids: list) -> dict:
        if not sale_ids:
            return {}
        result = await self.session.execute(
            select(Payment.sale_id, Payment.payment_method).where(
                Payment.sale_id.in_(sale_ids), Payment.payment_type == "SALE_PAYMENT"
            )
        )
        return {sale_id: method for sale_id, method in result.all()}

    async def sales_report(
        self,
        *,
        q: str | None,
        customer_id,
        product_id,
        category_id,
        cashier_id,
        payment_method: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        start_at, end_at = _range(start, end)

        def apply_filters(target):
            target = target.where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
            if q:
                target = target.where(Sale.invoice_no.ilike(f"%{q.strip()}%"))
            if customer_id is not None:
                target = target.where(Sale.customer_id == customer_id)
            if product_id is not None:
                target = target.where(SaleItem.product_id == product_id)
            if category_id is not None:
                target = target.where(Product.category_id == category_id)
            if cashier_id is not None:
                target = target.where(Sale.cashier_id == cashier_id)
            if payment_method == "CUSTOMER_DEBT":
                target = target.where(Sale.debt_amount > 0)
            elif payment_method in ("CASH", "BANK_QR"):
                # Fully tendered sales only: exclude debt sales whose deposit
                # was also paid in this method.
                target = target.where(Sale.debt_amount == 0).where(
                    Sale.id.in_(
                        select(Payment.sale_id).where(
                            Payment.payment_type == "SALE_PAYMENT", Payment.payment_method == payment_method
                        )
                    )
                )
            return target

        stmt = apply_filters(self._sales_query())
        count_stmt = apply_filters(
            select(func.count())
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id, isouter=True)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(Sale.sale_date.desc(), SaleItem.id)
                    .offset((page - 1) * limit)
                    .limit(limit)
                )
            ).all()
        )
        methods = await self._payment_methods([row.id for row in rows])

        data = []
        for row in rows:
            # Debt sales (any remaining credit) are reported as CUSTOMER_DEBT,
            # tendered sales carry their payment method, unpaid debt shows UNPAID.
            if Decimal(row.debt_amount) > 0:
                method = "CUSTOMER_DEBT"
            else:
                method = methods.get(row.id, "UNPAID")
            data.append(self._sales_row(row, method))
        return data, int(total)

    async def sales_report_export(self, **filters) -> list[dict]:
        filters["page"] = 1
        filters["limit"] = EXPORT_ROW_LIMIT
        rows, _ = await self.sales_report(**filters)
        return rows

    # ------------------------------------------------------- purchase report

    def _purchase_query(self) -> select:
        # Tender recorded for the stock-in (the earliest payment on the
        # purchase document) — shown as the Purchase Report Payment Method.
        payment_method = (
            select(Payment.payment_method)
            .where(Payment.reference_no == StockTransaction.document_no)
            .where(Payment.payment_type.in_(("STOCK_IN_PAYMENT", "SUPPLIER_DEBT_PAYMENT")))
            .order_by(Payment.created_at)
            .limit(1)
            .correlate(StockTransaction)
            .scalar_subquery()
            .label("payment_method")
        )
        return (
            select(
                StockTransaction.id,
                StockTransaction.document_no,
                StockTransaction.transaction_date,
                Supplier.name.label("supplier_name"),
                StockTransactionItem.product_name.label("product_name"),
                StockTransactionItem.id.label("stock_transaction_item_id"),
                StockTransactionItem.product_id.label("product_id"),
                StockTransactionItem.quantity,
                StockTransactionItem.returned_quantity,
                StockTransactionItem.unit_cost,
                StockTransactionItem.line_total,
                # Batch traceability: the lot/expiry the line was received into.
                # Needed so the purchase Edit form can reload the original lot.
                StockTransactionItem.batch_no,
                StockTransactionItem.expiry_date,
                StockTransaction.status,
                StockTransaction.currency,
                StockTransaction.exchange_rate,
                StockTransaction.note,
                StockTransaction.discount_amount,
                StockTransaction.tax_amount,
                User.full_name.label("created_by_name"),
                payment_method,
            )
            .select_from(StockTransactionItem)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .join(Supplier, Supplier.id == StockTransaction.supplier_id, isouter=True)
            .join(User, User.id == StockTransaction.created_by, isouter=True)
            .where(StockTransaction.transaction_type == "STOCK_IN")
        )

    async def purchase_report(
        self,
        *,
        q: str | None,
        supplier_id,
        product_id,
        status: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        start_at, end_at = _range(start, end)

        def apply_filters(target):
            target = target.where(
                StockTransaction.transaction_date >= start_at,
                StockTransaction.transaction_date < end_at,
            )
            if q:
                target = target.where(StockTransaction.document_no.ilike(f"%{q.strip()}%"))
            if supplier_id is not None:
                target = target.where(StockTransaction.supplier_id == supplier_id)
            if product_id is not None:
                target = target.where(StockTransactionItem.product_id == product_id)
            if status:
                target = target.where(StockTransaction.status == status)
            return target

        stmt = apply_filters(self._purchase_query())
        count_stmt = apply_filters(
            select(func.count())
            .select_from(StockTransactionItem)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        rows = await self.session.execute(
            stmt.order_by(StockTransaction.transaction_date.desc(), StockTransactionItem.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        raw = rows.all()

        transaction_ids = list({row.id for row in raw})
        debts: dict = {}
        if transaction_ids:
            debt_rows = await self.session.execute(
                select(SupplierDebt).where(SupplierDebt.stock_transaction_id.in_(transaction_ids))
            )
            debts = {debt.stock_transaction_id: debt for debt in debt_rows.scalars().all()}

        # In-stock quantity per line's lot: a purchase return can only take
        # back what is still physically on hand (the rest was already sold).
        from app.modules.stock.models import BatchStockBalance

        product_ids = {row.product_id for row in raw if row.product_id}
        lot_remaining: dict[tuple, Decimal] = {}
        product_remaining: dict = {}
        if product_ids:
            batch_rows = await self.session.execute(
                select(
                    BatchStockBalance.product_id,
                    BatchStockBalance.batch_no,
                    BatchStockBalance.expiry_date,
                    BatchStockBalance.remaining_quantity,
                ).where(BatchStockBalance.product_id.in_(product_ids))
            )
            for pid, batch_no, expiry_date, remaining in batch_rows.all():
                amount = Decimal(remaining or 0)
                lot_remaining[(pid, batch_no or "", expiry_date)] = (
                    lot_remaining.get((pid, batch_no or "", expiry_date), Decimal("0")) + amount
                )
                product_remaining[pid] = product_remaining.get(pid, Decimal("0")) + amount

        data = []
        for row in raw:
            debt = debts.get(row.id)
            remaining = Decimal(debt.remaining_amount) if debt else Decimal("0.00")
            quantity = Decimal(row.quantity)
            returned = Decimal(row.returned_quantity)
            unit_cost = Decimal(row.unit_cost)
            data.append(
                {
                    "transaction_id": row.id,
                    "stock_transaction_item_id": row.stock_transaction_item_id,
                    "product_id": row.product_id,
                    "document_no": row.document_no,
                    "transaction_date": row.transaction_date,
                    "supplier_name": row.supplier_name,
                    "product_name": row.product_name,
                    "quantity": quantity,
                    "returned_quantity": returned,
                    "returnable_quantity": (quantity - returned).quantize(Q4),
                    # Still physically in stock for this line's lot (purchase
                    # return caps at min(returnable, available)).
                    "available_quantity": (
                        lot_remaining.get(
                            (row.product_id, row.batch_no or "", row.expiry_date), Decimal("0")
                        )
                        if (row.batch_no or "").strip()
                        else product_remaining.get(row.product_id, Decimal("0"))
                    ).quantize(Q4),
                    "return_amount": (returned * unit_cost).quantize(Q2),
                    "cost_price": unit_cost,
                    "total_cost": Decimal(row.line_total),
                    # Batch traceability reloaded by the purchase Edit form.
                    "batch_no": row.batch_no,
                    "expiry_date": row.expiry_date,
                    "paid_amount": Decimal(row.line_total) - remaining if debt else Decimal(row.line_total),
                    "remaining_debt": remaining,
                    "status": debt.status if debt else "PAID",
                    "currency": row.currency,
                    "exchange_rate": row.exchange_rate,
                    # Header fields the purchase Edit form reloads (repeated
                    # per line; the SPA groups rows client-side).
                    "note": row.note,
                    "discount_amount": Decimal(row.discount_amount or 0),
                    "tax_amount": Decimal(row.tax_amount or 0),
                    "payment_method": row.payment_method,
                    "created_by_name": row.created_by_name,
                    "user": row.created_by_name,
                }
            )
        return data, int(total)

    # ---------------------------------------------------------- debt reports

    async def customer_debt_report(
        self,
        *,
        q: str | None,
        customer_id,
        status: str | None,
        currency: str | None = None,
        user_id=None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Invoice-level customer debt rows (spec 2.1.10 Customer Debt Report).

        The Date column/filter is the invoice (sale) date; every UNPAID,
        PARTIAL and PAID debt document is one row. `currency` is an optional
        document-currency filter — USD and KHR rows are never mixed.
        `user_id` narrows to the cashier who created the source sale.
        """
        start_at, end_at = _range(start, end)

        def apply_filters(target):
            target = target.where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
            if q:
                pattern = f"%{q.strip()}%"
                target = target.where(
                    CustomerDebt.invoice_no.ilike(pattern)
                    | Customer.name.ilike(pattern)
                    | Customer.code.ilike(pattern)
                )
            if customer_id is not None:
                target = target.where(CustomerDebt.customer_id == customer_id)
            if status:
                target = target.where(CustomerDebt.status == status)
            if currency:
                target = target.where(CustomerDebt.currency == currency)
            if user_id is not None:
                target = target.where(Sale.cashier_id == user_id)
            return target

        base = (
            select(CustomerDebt, Customer.name, Customer.code, Sale.sale_date, Sale.cashier_id, User.full_name)
            .join(Customer, Customer.id == CustomerDebt.customer_id)
            .join(Sale, Sale.id == CustomerDebt.sale_id)
            .outerjoin(User, User.id == Sale.cashier_id)
        )
        count_base = (
            select(func.count())
            .select_from(CustomerDebt)
            .join(Customer, Customer.id == CustomerDebt.customer_id)
            .join(Sale, Sale.id == CustomerDebt.sale_id)
        )
        total = (await self.session.execute(apply_filters(count_base))).scalar_one()
        rows = await self.session.execute(
            apply_filters(base)
            .order_by(Sale.sale_date.desc(), CustomerDebt.created_at.desc(), CustomerDebt.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        data = [
            {
                "debt_id": debt.id,
                "customer_id": debt.customer_id,
                "customer_name": name,
                "customer_code": code,
                "date": sale_date,
                "invoice_no": debt.invoice_no,
                "invoice_total": debt.original_amount,
                "paid_amount": debt.paid_amount,
                "remaining_amount": debt.remaining_amount,
                "due_date": debt.due_date,
                "status": debt.status,
                "currency": debt.currency,
                "exchange_rate": debt.exchange_rate,
                "user_id": cashier_id,
                "user_name": user_name,
                "created_at": debt.created_at,
            }
            for debt, name, code, sale_date, cashier_id, user_name in rows.all()
        ]
        return data, int(total)

    async def supplier_debt_report(
        self,
        *,
        q: str | None,
        supplier_id,
        status: str | None,
        currency: str | None = None,
        user_id=None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Document-level supplier debt rows (spec 2.1.10 Supplier Debt Report).

        The Date column/filter is the stock-in / purchase date; every UNPAID,
        PARTIAL and PAID debt document is one row. `currency` is an optional
        document-currency filter — USD and KHR rows are never mixed.
        `user_id` narrows to the user who created the source Stock In.
        """
        start_at, end_at = _range(start, end)

        def apply_filters(target):
            target = target.where(
                StockTransaction.transaction_date >= start_at,
                StockTransaction.transaction_date < end_at,
            )
            if q:
                pattern = f"%{q.strip()}%"
                target = target.where(
                    SupplierDebt.document_no.ilike(pattern)
                    | Supplier.name.ilike(pattern)
                    | Supplier.code.ilike(pattern)
                )
            if supplier_id is not None:
                target = target.where(SupplierDebt.supplier_id == supplier_id)
            if status:
                target = target.where(SupplierDebt.status == status)
            if currency:
                target = target.where(SupplierDebt.currency == currency)
            if user_id is not None:
                target = target.where(StockTransaction.created_by == user_id)
            return target

        base = (
            select(
                SupplierDebt,
                Supplier.name,
                Supplier.code,
                StockTransaction.transaction_date,
                StockTransaction.created_by,
                User.full_name,
            )
            .join(Supplier, Supplier.id == SupplierDebt.supplier_id)
            .join(StockTransaction, StockTransaction.id == SupplierDebt.stock_transaction_id)
            .outerjoin(User, User.id == StockTransaction.created_by)
        )
        count_base = (
            select(func.count())
            .select_from(SupplierDebt)
            .join(Supplier, Supplier.id == SupplierDebt.supplier_id)
            .join(StockTransaction, StockTransaction.id == SupplierDebt.stock_transaction_id)
        )
        total = (await self.session.execute(apply_filters(count_base))).scalar_one()
        rows = await self.session.execute(
            apply_filters(base)
            .order_by(
                StockTransaction.transaction_date.desc(),
                SupplierDebt.created_at.desc(),
                SupplierDebt.id,
            )
            .offset((page - 1) * limit)
            .limit(limit)
        )
        data = [
            {
                "debt_id": debt.id,
                "supplier_id": debt.supplier_id,
                "supplier_name": name,
                "supplier_code": code,
                "date": transaction_date,
                "document_no": debt.document_no,
                "total_amount": debt.original_amount,
                "paid_amount": debt.paid_amount,
                "remaining_amount": debt.remaining_amount,
                "due_date": debt.due_date,
                "status": debt.status,
                "currency": debt.currency,
                "exchange_rate": debt.exchange_rate,
                "user_id": created_by,
                "user_name": user_name,
                "created_at": debt.created_at,
            }
            for debt, name, code, transaction_date, created_by, user_name in rows.all()
        ]
        return data, int(total)

    # --------------------------------------------------------- finance report

    async def finance_report(self, *, start: date | None, end: date | None) -> dict:
        start_at, end_at = _range(start, end)
        period_start = start_at.date()
        period_end = end_at.date() - timedelta(days=1)

        sales_total = await self.session.execute(
            select(func.coalesce(func.sum(_usd(Sale.grand_total, Sale.currency, Sale.exchange_rate)), 0)).where(
                Sale.sale_date >= start_at, Sale.sale_date < end_at
            )
        )
        refunds = await self.session.execute(
            select(func.coalesce(func.sum(_usd(SaleReturn.refund_amount, Sale.currency, Sale.exchange_rate)), 0))
            .select_from(SaleReturn)
            .join(Sale, Sale.id == SaleReturn.sale_id)
            .where(
                SaleReturn.return_date >= start_at, SaleReturn.return_date < end_at
            )
        )
        purchase_total = await self.session.execute(
            select(func.coalesce(func.sum(_usd(StockTransactionItem.line_total, StockTransaction.currency, StockTransaction.exchange_rate)), 0))
            .select_from(StockTransactionItem)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .where(
                StockTransaction.transaction_type == "STOCK_IN",
                StockTransaction.transaction_date >= start_at,
                StockTransaction.transaction_date < end_at,
            )
        )
        customer_debt = await self.session.execute(
            select(func.coalesce(func.sum(_usd(CustomerDebt.remaining_amount, CustomerDebt.currency, CustomerDebt.exchange_rate)), 0))
        )
        supplier_debt = await self.session.execute(
            select(func.coalesce(func.sum(_usd(SupplierDebt.remaining_amount, SupplierDebt.currency, SupplierDebt.exchange_rate)), 0))
        )
        operating_expense = await self.session.execute(
            select(func.coalesce(func.sum(_usd(Expense.amount, Expense.currency, Expense.exchange_rate)), 0)).where(
                Expense.status == "POSTED",
                Expense.expense_date >= start_at.date(),
                Expense.expense_date < end_at.date(),
            )
        )
        # Cash actually paid to suppliers in the period: the payment made when a
        # purchase is received (full or partial) plus every later debt
        # repayment. Each payment row is a single cash-out, so a purchase and
        # its repayments are never counted twice.
        supplier_payment_rows = self._finance_supplier_payment_stmt().subquery()
        supplier_payment = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        _usd(
                            supplier_payment_rows.c.amount,
                            supplier_payment_rows.c.currency,
                            supplier_payment_rows.c.exchange_rate,
                        )
                    ),
                    0,
                )
            ).where(
                supplier_payment_rows.c.entry_date >= start_at,
                supplier_payment_rows.c.entry_date < end_at,
            )
        )

        # Damage/expiry losses come from the movement cost ledger, which is
        # recorded per movement (base-unit cost at mutation time) and has no
        # document currency — those sums stay as recorded.
        async def loss(movement_type: str) -> Decimal:
            result = await self.session.execute(
                select(
                    func.coalesce(func.sum(-StockMovement.quantity_delta * StockMovement.unit_cost), 0)
                ).where(
                    StockMovement.movement_type == movement_type,
                    StockMovement.quantity_delta < 0,
                    StockMovement.created_at >= start_at,
                    StockMovement.created_at < end_at,
                )
            )
            return Decimal(result.scalar_one())

        damage_loss = await loss("DAMAGE")
        expiry_loss = await loss("EXPIRE")

        # COGS per sold line: exact per-batch cost snapshot when present
        # (sale_item_batches), else the sale item's unit_cost × base quantity.
        batch_costs = (
            select(
                SaleItemBatch.sale_item_id.label("sale_item_id"),
                func.sum(SaleItemBatch.quantity_base * SaleItemBatch.cost_per_base).label("batch_cost"),
            )
            .group_by(SaleItemBatch.sale_item_id)
            .subquery()
        )
        sold = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            batch_costs.c.batch_cost,
                            SaleItem.unit_cost * SaleItem.quantity * SaleItem.factor_to_base,
                        )
                    ),
                    0,
                )
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(batch_costs, batch_costs.c.sale_item_id == SaleItem.id, isouter=True)
            .where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
        )
        restocked = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            batch_costs.c.batch_cost * SaleReturnItem.quantity / SaleItem.quantity,
                            SaleReturnItem.quantity * SaleItem.unit_cost * SaleItem.factor_to_base,
                        )
                    ),
                    0,
                )
            )
            .select_from(SaleReturnItem)
            .join(SaleItem, SaleItem.id == SaleReturnItem.sale_item_id)
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(batch_costs, batch_costs.c.sale_item_id == SaleItem.id, isouter=True)
            .where(
                SaleReturnItem.restock.is_(True),
                SaleReturn.return_date >= start_at,
                SaleReturn.return_date < end_at,
            )
        )

        gross_sales = Decimal(sales_total.scalar_one())
        sale_returns = Decimal(refunds.scalar_one())
        purchase_cost = Decimal(purchase_total.scalar_one())
        customer_debt_total = Decimal(customer_debt.scalar_one())
        supplier_debt_total = Decimal(supplier_debt.scalar_one())
        operating_expenses = Decimal(operating_expense.scalar_one())
        supplier_payments = Decimal(supplier_payment.scalar_one())

        net_sales = gross_sales - sale_returns
        cogs = Decimal(sold.scalar_one()) - Decimal(restocked.scalar_one())
        gross_profit = net_sales - cogs
        # Accounting profit NEVER subtracts supplier payments: the inventory cost
        # is already recognized through COGS. Supplier cash-out belongs to the
        # separate cash-flow view below.
        operating_profit = gross_profit - damage_loss - expiry_loss - operating_expenses
        cash_flow = await self._cash_flow_totals(start_at, end_at)

        return {
            "period_start": period_start,
            "period_end": period_end,
            "report_currency": REPORT_CURRENCY,
            # ---- Legacy flattened cards (kept for existing clients) ----------
            # `total_sales` is net of returns; `total_expense` is the combined
            # cash view (operating expenses + supplier payments) and is NOT the
            # P&L expense. Use `profit_and_loss` / `cash_flow` for reporting.
            "total_sales": net_sales,
            "total_expense": operating_expenses + supplier_payments,
            "total_purchase_cost": purchase_cost,
            "total_customer_debt": customer_debt_total,
            "total_supplier_debt": supplier_debt_total,
            "cost_of_goods_sold": cogs,
            "stock_damage_loss": damage_loss,
            "stock_expire_loss": expiry_loss,
            "gross_profit": gross_profit,
            "operating_expenses": operating_expenses,
            "supplier_payments": supplier_payments,
            "net_result": operating_profit,
            # ---- Profit & Loss (accrual/accounting view) ---------------------
            "profit_and_loss": {
                "gross_sales": gross_sales,
                "sale_returns": sale_returns,
                "net_sales": net_sales,
                "cost_of_goods_sold": cogs,
                "gross_profit": gross_profit,
                "operating_expenses": operating_expenses,
                "stock_damage_loss": damage_loss,
                "stock_expire_loss": expiry_loss,
                "operating_profit": operating_profit,
            },
            # ---- Cash Flow (cash-basis view) ---------------------------------
            "cash_flow": cash_flow,
        }

    def _finance_refund_stmt(self, payment_types: tuple[str, ...]) -> select:
        """Payment rows for sale refunds (cash-out) / supplier refund credits.

        Currency inherits the linked document snapshot (the sale for
        SALE_REFUND, the supplier debt/purchase for SUPPLIER_RETURN_CREDIT) so
        normalization never uses the shop's current rate."""
        sale = aliased(Sale)
        return (
            select(
                Payment.id.label("id"),
                Payment.created_at.label("entry_date"),
                Payment.amount.label("amount"),
                Payment.payment_method.label("payment_method"),
                func.coalesce(sale.currency, SupplierDebt.currency, literal("USD")).label("currency"),
                func.coalesce(sale.exchange_rate, SupplierDebt.exchange_rate, literal(1)).label(
                    "exchange_rate"
                ),
            )
            .select_from(Payment)
            .outerjoin(sale, sale.id == Payment.sale_id)
            .outerjoin(SupplierDebt, SupplierDebt.id == Payment.supplier_debt_id)
            .where(Payment.payment_type.in_(payment_types))
        )

    async def _cash_flow_totals(self, start_at: datetime, end_at: datetime) -> dict:
        """Cash-basis inflow/outflow for the period (spec: cash flow).

        Unpaid credit sales are never inflow, unpaid purchases are never
        outflow. Supplier refunds count only when actually received in
        cash/bank (a supplier credit is not a cash movement)."""
        income = self._finance_income_stmt().subquery()

        async def _sum_income(*, sales: bool) -> Decimal:
            condition = income.c.category == "Sales" if sales else income.c.category != "Sales"
            result = await self.session.execute(
                select(
                    func.coalesce(
                        func.sum(_usd(income.c.amount, income.c.currency, income.c.exchange_rate)), 0
                    )
                ).where(
                    income.c.entry_date >= start_at,
                    income.c.entry_date < end_at,
                    condition,
                )
            )
            return Decimal(result.scalar_one())

        sale_receipts = await _sum_income(sales=True)
        debt_collections = await _sum_income(sales=False)

        supplier = self._finance_supplier_payment_stmt().subquery()
        supplier_result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(_usd(supplier.c.amount, supplier.c.currency, supplier.c.exchange_rate)), 0
                )
            ).where(supplier.c.entry_date >= start_at, supplier.c.entry_date < end_at)
        )
        supplier_payments = Decimal(supplier_result.scalar_one())

        supplier_refunds = self._finance_refund_stmt(("SUPPLIER_RETURN_CREDIT",)).subquery()
        supplier_refund_result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        _usd(
                            supplier_refunds.c.amount,
                            supplier_refunds.c.currency,
                            supplier_refunds.c.exchange_rate,
                        )
                    ),
                    0,
                )
            ).where(
                supplier_refunds.c.entry_date >= start_at,
                supplier_refunds.c.entry_date < end_at,
                supplier_refunds.c.payment_method.in_(("CASH", "BANK_QR")),
            )
        )
        supplier_refunds_received = Decimal(supplier_refund_result.scalar_one())

        refunds = self._finance_refund_stmt(("SALE_REFUND",)).subquery()
        refund_result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(_usd(refunds.c.amount, refunds.c.currency, refunds.c.exchange_rate)), 0
                )
            ).where(refunds.c.entry_date >= start_at, refunds.c.entry_date < end_at)
        )
        customer_refunds = Decimal(refund_result.scalar_one())

        expense = await self.session.execute(
            select(
                func.coalesce(func.sum(_usd(Expense.amount, Expense.currency, Expense.exchange_rate)), 0)
            ).where(
                Expense.status == "POSTED",
                Expense.expense_date >= start_at.date(),
                Expense.expense_date < end_at.date(),
            )
        )
        operating_expenses = Decimal(expense.scalar_one())

        total_inflow = sale_receipts + debt_collections + supplier_refunds_received
        total_outflow = supplier_payments + customer_refunds + operating_expenses
        return {
            "sale_receipts": sale_receipts,
            "debt_collections": debt_collections,
            "supplier_refunds_received": supplier_refunds_received,
            "total_inflow": total_inflow,
            "supplier_payments": supplier_payments,
            "customer_refunds_paid": customer_refunds,
            "operating_expenses": operating_expenses,
            "total_outflow": total_outflow,
            "net_cash_flow": total_inflow - total_outflow,
        }

    # ------------------------------------------------- finance entries (table)

    def _finance_income_stmt(self) -> select:
        """Income rows = customer cash actually received (never manually added).

        Cash-basis: the tender taken at checkout (`SALE_PAYMENT`) plus every
        later customer-debt collection (`CUSTOMER_DEBT_PAYMENT`). A credit sale
        only becomes income when the customer pays, so unpaid debt never
        inflates income and collections always show as their own row."""
        sale = aliased(Sale)
        debt = aliased(CustomerDebt)
        debt_sale = aliased(Sale)
        return (
            select(
                Payment.id.label("id"),
                Payment.created_at.label("entry_date"),
                literal("income", type_=String).label("entry_type"),
                func.coalesce(
                    sale.invoice_no,
                    Payment.reference_no,
                    debt_sale.invoice_no,
                    Payment.payment_no,
                ).label("reference"),
                case(
                    (Payment.payment_type == "SALE_PAYMENT", literal("Sales")),
                    else_=literal("Customer Payment"),
                ).label("category"),
                func.coalesce(Customer.name, literal("")).label("description"),
                Payment.amount.label("amount"),
                # Payment has no currency of its own: inherit the sale's
                # document currency (directly, or via the debt it settles).
                func.coalesce(sale.currency, debt_sale.currency, literal("USD")).label("currency"),
                func.coalesce(sale.exchange_rate, debt_sale.exchange_rate, literal(1)).label("exchange_rate"),
                Payment.payment_method.label("payment_method"),
                func.coalesce(User.full_name, literal("")).label("created_by_name"),
                Payment.created_at.label("created_at"),
            )
            .select_from(Payment)
            .outerjoin(sale, sale.id == Payment.sale_id)
            .outerjoin(Customer, Customer.id == Payment.customer_id)
            .outerjoin(User, User.id == Payment.created_by)
            .outerjoin(debt, debt.id == Payment.customer_debt_id)
            .outerjoin(debt_sale, debt_sale.id == debt.sale_id)
            .where(Payment.payment_type.in_(("SALE_PAYMENT", "CUSTOMER_DEBT_PAYMENT")))
        )

    def _finance_expense_stmt(self) -> select:
        """Expense rows from user-recorded operating expenses."""
        return (
            select(
                Expense.id.label("id"),
                cast(Expense.expense_date, DateTime(timezone=True)).label("entry_date"),
                literal("expense", type_=String).label("entry_type"),
                func.coalesce(Expense.reference, Expense.category).label("reference"),
                Expense.category.label("category"),
                Expense.description.label("description"),
                Expense.amount.label("amount"),
                Expense.currency.label("currency"),
                Expense.exchange_rate.label("exchange_rate"),
                func.coalesce(Expense.payment_method, literal("")).label("payment_method"),
                func.coalesce(User.full_name, literal("")).label("created_by_name"),
                Expense.created_at.label("created_at"),
            )
            .select_from(Expense)
            .join(User, User.id == Expense.created_by)
            # Only POSTED expenses affect reports/cash flow.
            .where(Expense.status == "POSTED")
        )

    def _finance_supplier_payment_stmt(self) -> select:
        """Expense rows for cash paid to suppliers.

        Every purchase creates one immutable `Payment` for the amount paid at
        receipt (`STOCK_IN_PAYMENT` when settled in full, `SUPPLIER_DEBT_PAYMENT`
        when part is left on credit) and each later repayment adds another
        `SUPPLIER_DEBT_PAYMENT`. Summing these rows gives the true supplier
        cash-out without counting a purchase and its repayment twice.
        """
        purchase = aliased(StockTransaction)
        return (
            select(
                Payment.id.label("id"),
                Payment.created_at.label("entry_date"),
                literal("expense", type_=String).label("entry_type"),
                func.coalesce(Payment.reference_no, Payment.payment_no).label("reference"),
                case(
                    (Payment.payment_type == "STOCK_IN_PAYMENT", literal("Purchase")),
                    else_=literal("Supplier Payment"),
                ).label("category"),
                func.coalesce(Supplier.name, literal("")).label("description"),
                Payment.amount.label("amount"),
                func.coalesce(SupplierDebt.currency, purchase.currency, literal("USD")).label("currency"),
                func.coalesce(SupplierDebt.exchange_rate, purchase.exchange_rate, literal(1)).label("exchange_rate"),
                Payment.payment_method.label("payment_method"),
                func.coalesce(User.full_name, literal("")).label("created_by_name"),
                Payment.created_at.label("created_at"),
            )
            .select_from(Payment)
            .outerjoin(SupplierDebt, SupplierDebt.id == Payment.supplier_debt_id)
            .outerjoin(purchase, purchase.document_no == Payment.reference_no)
            .outerjoin(Supplier, Supplier.id == Payment.supplier_id)
            .outerjoin(User, User.id == Payment.created_by)
            .where(Payment.payment_type.in_(("STOCK_IN_PAYMENT", "SUPPLIER_DEBT_PAYMENT")))
        )

    async def finance_entries(
        self,
        *,
        q: str | None,
        entry_type: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Combined income + expense ledger table with date/type/search filters."""
        start_at, end_at = _range(start, end)
        union = (
            self._finance_income_stmt()
            .union_all(
                self._finance_expense_stmt(),
                self._finance_supplier_payment_stmt(),
            )
            .subquery()
        )

        # Accept INCOME|EXPENSE and lowercase variants.
        normalized_type = entry_type.strip().lower() if entry_type else None

        def apply_filters(target):
            target = target.where(union.c.entry_date >= start_at, union.c.entry_date < end_at)
            if normalized_type:
                target = target.where(union.c.entry_type == normalized_type)
            if q:
                pattern = f"%{q.strip()}%"
                target = target.where(
                    union.c.reference.ilike(pattern) | union.c.description.ilike(pattern)
                )
            return target

        rows_stmt = apply_filters(select(union)).order_by(
            union.c.entry_date.desc(), union.c.created_at.desc(), union.c.id
        )
        count_stmt = apply_filters(select(func.count()).select_from(union))
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = (await self.session.execute(rows_stmt.offset((page - 1) * limit).limit(limit))).all()
        data = [
            {
                "id": row.id,
                "date": row.entry_date,
                "type": row.entry_type,
                "reference": row.reference,
                "category": row.category,
                "description": row.description,
                "amount": Decimal(row.amount),
                "currency": row.currency,
                "exchange_rate": row.exchange_rate,
                "payment_method": row.payment_method or None,
                "paymentMethod": row.payment_method or None,
                "created_by_name": row.created_by_name,
                "user": row.created_by_name,
                "created_at": row.created_at,
            }
            for row in rows
        ]
        return data, int(total)

    # -------------------------------------------------------- create expense

    async def create_expense(self, *, payload: ExpenseCreate, actor: User) -> Expense:
        """Record one operating expense (Finance Report only) with audit.

        Defaults to POSTED (affects reports/cash flow); DRAFT is available for
        a review-then-post workflow."""
        amount = payload.amount.quantize(Q2)
        if amount <= 0:
            raise ValidationError("Expense amount must be greater than zero")
        now = datetime.now(timezone.utc)
        posted = payload.status == "POSTED"
        expense = Expense(
            expense_date=payload.date,
            category=payload.category.strip(),
            description=(payload.description or "").strip() or None,
            reference=(payload.reference or "").strip() or None,
            amount=amount,
            payment_method=payload.payment_method,
            currency=payload.currency,
            exchange_rate=payload.exchange_rate,
            status=payload.status,
            posting_date=(payload.posting_date or payload.date) if posted else None,
            approved_by=actor.id if posted else None,
            approved_at=now if posted else None,
            attachment_object_key=payload.attachment_object_key,
            created_by=actor.id,
        )
        self.session.add(expense)
        await self.session.flush()
        await record_audit(
            self.session,
            action="expense_created",
            module="reports",
            user_id=actor.id,
            entity_type="expense",
            entity_id=expense.id,
            new_values={
                "expense_date": payload.date.isoformat(),
                "category": expense.category,
                "description": expense.description,
                "amount": str(amount),
                "payment_method": expense.payment_method,
                "status": expense.status,
            },
        )
        await self.session.commit()
        return expense

    async def get_expense(self, expense_id) -> Expense:
        expense = await self.session.get(Expense, expense_id)
        if expense is None:
            raise ValidationError("Expense not found")
        return expense

    async def update_expense(self, expense_id, payload, *, actor: User) -> Expense:
        """Edit a DRAFT expense only; posted expenses are immutable."""
        expense = await self.session.get(Expense, expense_id, with_for_update=True)
        if expense is None:
            raise ValidationError("Expense not found")
        if expense.status != "DRAFT":
            raise ConflictError("Only draft expenses can be edited; void and replace instead")
        old = {
            "category": expense.category,
            "amount": str(expense.amount),
            "status": expense.status,
        }
        if payload.expense_date is not None:
            expense.expense_date = payload.expense_date
        if payload.category is not None:
            expense.category = payload.category.strip()
        if payload.description is not None:
            expense.description = payload.description.strip() or None
        if payload.reference is not None:
            expense.reference = payload.reference.strip() or None
        if payload.amount is not None:
            amount = payload.amount.quantize(Q2)
            if amount <= 0:
                raise ValidationError("Expense amount must be greater than zero")
            expense.amount = amount
        if payload.payment_method is not None:
            expense.payment_method = payload.payment_method
        if payload.currency is not None:
            expense.currency = payload.currency
        if payload.exchange_rate is not None:
            expense.exchange_rate = payload.exchange_rate
        if payload.attachment_object_key is not None:
            expense.attachment_object_key = payload.attachment_object_key
        await self.session.flush()
        await record_audit(
            self.session,
            action="expense_updated",
            module="reports",
            user_id=actor.id,
            entity_type="expense",
            entity_id=expense.id,
            old_values=old,
            new_values={"category": expense.category, "amount": str(expense.amount)},
        )
        await self.session.commit()
        return expense

    async def post_expense(self, expense_id, *, actor: User) -> Expense:
        """Approve/post a draft expense so it starts affecting reports."""
        expense = await self.session.get(Expense, expense_id, with_for_update=True)
        if expense is None:
            raise ValidationError("Expense not found")
        if expense.status == "VOID":
            raise ConflictError("A voided expense cannot be posted")
        if expense.status == "POSTED":
            return expense
        expense.status = "POSTED"
        expense.posting_date = expense.posting_date or expense.expense_date
        expense.approved_by = actor.id
        expense.approved_at = datetime.now(timezone.utc)
        await self.session.flush()
        await record_audit(
            self.session,
            action="expense_posted",
            module="reports",
            user_id=actor.id,
            entity_type="expense",
            entity_id=expense.id,
            new_values={"status": "POSTED", "posting_date": expense.posting_date.isoformat()},
        )
        await self.session.commit()
        return expense

    async def void_expense(self, expense_id, reason: str, *, actor: User) -> Expense:
        """Void an expense (corrections use void + replacement, never delete)."""
        expense = await self.session.get(Expense, expense_id, with_for_update=True)
        if expense is None:
            raise ValidationError("Expense not found")
        if expense.status == "VOID":
            raise ConflictError("This expense is already void")
        expense.status = "VOID"
        expense.void_reason = reason.strip()
        expense.voided_by = actor.id
        expense.voided_at = datetime.now(timezone.utc)
        await self.session.flush()
        await record_audit(
            self.session,
            action="expense_voided",
            module="reports",
            user_id=actor.id,
            entity_type="expense",
            entity_id=expense.id,
            new_values={"status": "VOID", "reason": expense.void_reason},
        )
        await self.session.commit()
        return expense

    # ------------------------------------------------------- returns history

    @staticmethod
    def _sale_return_items_agg():
        """Per-return item count + restocked quantity (restock=True lines)."""
        return (
            select(
                SaleReturnItem.sale_return_id.label("return_id"),
                func.count().label("item_count"),
                func.coalesce(
                    func.sum(
                        case((SaleReturnItem.restock.is_(True), SaleReturnItem.quantity), else_=literal(0))
                    ),
                    0,
                ).label("restocked_quantity"),
            )
            .group_by(SaleReturnItem.sale_return_id)
            .subquery()
        )

    async def sale_returns_report(
        self,
        *,
        q: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Customer-return history: one row per immutable sale_returns doc."""
        start_at, end_at = _range(start, end)
        items_agg = self._sale_return_items_agg()

        def apply_filters(target):
            target = target.where(SaleReturn.return_date >= start_at, SaleReturn.return_date < end_at)
            if q:
                term = f"%{q.strip()}%"
                target = target.where(
                    or_(
                        SaleReturn.return_no.ilike(term),
                        Sale.invoice_no.ilike(term),
                        Customer.name.ilike(term),
                        SaleReturn.reason.ilike(term),
                    )
                )
            return target

        def base_query():
            return (
                select(
                    SaleReturn.id,
                    SaleReturn.return_no,
                    SaleReturn.sale_id,
                    SaleReturn.return_date,
                    SaleReturn.refund_amount,
                    SaleReturn.reason,
                    Sale.invoice_no.label("sale_no"),
                    Customer.name.label("customer_name"),
                    User.full_name.label("user_name"),
                    items_agg.c.item_count,
                    items_agg.c.restocked_quantity,
                )
                .select_from(SaleReturn)
                .join(Sale, Sale.id == SaleReturn.sale_id)
                .join(Customer, Customer.id == Sale.customer_id, isouter=True)
                .join(User, User.id == SaleReturn.created_by, isouter=True)
                .join(items_agg, items_agg.c.return_id == SaleReturn.id, isouter=True)
            )

        stmt = apply_filters(base_query())
        count_stmt = apply_filters(
            select(func.count())
            .select_from(SaleReturn)
            .join(Sale, Sale.id == SaleReturn.sale_id)
            # Filters reference Customer.name — join it (outer) to avoid a
            # cartesian product in the count.
            .join(Customer, Customer.id == Sale.customer_id, isouter=True)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(SaleReturn.return_date.desc(), SaleReturn.return_no)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        data = [
            {
                "return_id": row.id,
                "return_no": row.return_no,
                "sale_id": row.sale_id,
                "sale_no": row.sale_no,
                "return_date": row.return_date,
                "customer_name": row.customer_name,
                "item_count": int(row.item_count or 0),
                "refund_amount": Decimal(row.refund_amount),
                "restocked_quantity": Decimal(row.restocked_quantity or 0),
                "reason": row.reason,
                "user_name": row.user_name,
            }
            for row in rows.all()
        ]
        return data, total

    @staticmethod
    def _purchase_return_items_agg():
        """Per-return item count for supplier-return history."""
        return (
            select(
                PurchaseReturnItem.purchase_return_id.label("return_id"),
                func.count().label("item_count"),
            )
            .group_by(PurchaseReturnItem.purchase_return_id)
            .subquery()
        )

    async def purchase_returns_report(
        self,
        *,
        q: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Supplier-return history: one row per immutable purchase_returns doc."""
        start_at, end_at = _range(start, end)
        items_agg = self._purchase_return_items_agg()

        def apply_filters(target):
            target = target.where(PurchaseReturn.return_date >= start_at, PurchaseReturn.return_date < end_at)
            if q:
                term = f"%{q.strip()}%"
                target = target.where(
                    or_(
                        PurchaseReturn.return_no.ilike(term),
                        StockTransaction.document_no.ilike(term),
                        Supplier.name.ilike(term),
                        PurchaseReturn.reason.ilike(term),
                    )
                )
            return target

        def base_query():
            return (
                select(
                    PurchaseReturn.id,
                    PurchaseReturn.return_no,
                    PurchaseReturn.stock_transaction_id,
                    PurchaseReturn.return_date,
                    PurchaseReturn.refund_amount,
                    PurchaseReturn.debt_reduction,
                    PurchaseReturn.credit_amount,
                    PurchaseReturn.reason,
                    StockTransaction.document_no,
                    Supplier.name.label("supplier_name"),
                    User.full_name.label("user_name"),
                    items_agg.c.item_count,
                )
                .select_from(PurchaseReturn)
                .join(
                    StockTransaction,
                    StockTransaction.id == PurchaseReturn.stock_transaction_id,
                )
                .join(Supplier, Supplier.id == PurchaseReturn.supplier_id, isouter=True)
                .join(User, User.id == PurchaseReturn.created_by, isouter=True)
                .join(items_agg, items_agg.c.return_id == PurchaseReturn.id, isouter=True)
            )

        stmt = apply_filters(base_query())
        count_stmt = apply_filters(
            select(func.count())
            .select_from(PurchaseReturn)
            .join(StockTransaction, StockTransaction.id == PurchaseReturn.stock_transaction_id)
            # Filters reference Supplier.name — join it (outer) to avoid a
            # cartesian product in the count.
            .join(Supplier, Supplier.id == PurchaseReturn.supplier_id, isouter=True)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(PurchaseReturn.return_date.desc(), PurchaseReturn.return_no)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        data = [
            {
                "return_id": row.id,
                "return_no": row.return_no,
                "stock_transaction_id": row.stock_transaction_id,
                "document_no": row.document_no,
                "return_date": row.return_date,
                "supplier_name": row.supplier_name,
                "item_count": int(row.item_count or 0),
                "refund_amount": Decimal(row.refund_amount),
                "debt_reduction": Decimal(row.debt_reduction),
                "credit_amount": Decimal(row.credit_amount),
                "reason": row.reason,
                "user_name": row.user_name,
            }
            for row in rows.all()
        ]
        return data, total

    # -------------------------------------------- stock valuation / recon

    async def inventory_valuation(self, *, as_of: date | None = None) -> dict:
        """Inventory valuation, batch-level.

        Current-date valuation uses the batch ledger (remaining x unit cost)
        plus any untracked balance at the moving-average cost. An explicit
        `as_of` date derives the quantity from the movement ledger up to that
        date and values it at the current average cost (a documented
        approximation: historical unit costs are not reconstructed)."""
        from app.modules.stock.models import BatchStockBalance, StockBalance

        batch_agg = (
            select(
                BatchStockBalance.product_id.label("product_id"),
                func.coalesce(func.sum(BatchStockBalance.remaining_quantity), 0).label("batch_qty"),
                func.coalesce(
                    func.sum(BatchStockBalance.remaining_quantity * BatchStockBalance.unit_cost), 0
                ).label("batch_value"),
            )
            .group_by(BatchStockBalance.product_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(
                Product.id,
                Product.name,
                func.coalesce(StockBalance.quantity, 0).label("balance_qty"),
                func.coalesce(StockBalance.average_cost, 0).label("average_cost"),
                func.coalesce(batch_agg.c.batch_qty, 0).label("batch_qty"),
                func.coalesce(batch_agg.c.batch_value, 0).label("batch_value"),
            )
            .select_from(Product)
            .outerjoin(StockBalance, StockBalance.product_id == Product.id)
            .outerjoin(batch_agg, batch_agg.c.product_id == Product.id)
            .where(Product.status == "ACTIVE")
            .order_by(Product.name)
        )
        movement_qty: dict = {}
        if as_of is not None:
            end_at = _day_start(as_of + timedelta(days=1))
            mv = await self.session.execute(
                select(
                    StockMovement.product_id,
                    func.coalesce(func.sum(StockMovement.quantity_delta), 0),
                )
                .where(StockMovement.created_at < end_at)
                .group_by(StockMovement.product_id)
            )
            movement_qty = {row[0]: Decimal(row[1]) for row in mv.all()}

        data = []
        total_value = Decimal("0.00")
        total_qty = Decimal("0.0000")
        for row in rows.all():
            balance_qty = Decimal(row.balance_qty)
            avg_cost = Decimal(row.average_cost)
            batch_qty = Decimal(row.batch_qty)
            batch_value = Decimal(row.batch_value)
            if as_of is not None:
                qty = movement_qty.get(row.id, Decimal("0"))
                value = (qty * avg_cost).quantize(Q2)
            else:
                qty = balance_qty
                # Batch value plus any untracked balance at average cost.
                untracked = max(Decimal("0"), balance_qty - batch_qty)
                value = (batch_value + untracked * avg_cost).quantize(Q2)
            total_value += value
            total_qty += qty
            data.append(
                {
                    "product_id": row.id,
                    "product_name": row.name,
                    "quantity": qty,
                    "batch_quantity": batch_qty,
                    "unit_cost": avg_cost,
                    "value": value,
                }
            )
        return {
            "as_of": as_of,
            "rows": data,
            "total_quantity": total_qty,
            "total_value": total_value.quantize(Q2),
        }

    async def stock_reconciliation(self) -> dict:
        """Reconcile stock_balances vs batch remaining vs movement ledger."""
        from app.modules.stock.models import BatchStockBalance, StockBalance

        batch_agg = (
            select(
                BatchStockBalance.product_id.label("product_id"),
                func.coalesce(func.sum(BatchStockBalance.remaining_quantity), 0).label("batch_qty"),
            )
            .group_by(BatchStockBalance.product_id)
            .subquery()
        )
        movement_agg = (
            select(
                StockMovement.product_id.label("product_id"),
                func.coalesce(func.sum(StockMovement.quantity_delta), 0).label("movement_qty"),
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(
                Product.id,
                Product.name,
                func.coalesce(StockBalance.quantity, 0).label("balance_qty"),
                func.coalesce(batch_agg.c.batch_qty, 0).label("batch_qty"),
                func.coalesce(movement_agg.c.movement_qty, 0).label("movement_qty"),
            )
            .select_from(Product)
            .outerjoin(StockBalance, StockBalance.product_id == Product.id)
            .outerjoin(batch_agg, batch_agg.c.product_id == Product.id)
            .outerjoin(movement_agg, movement_agg.c.product_id == Product.id)
            .order_by(Product.name)
        )
        mismatches = []
        for row in rows.all():
            balance_qty = Decimal(row.balance_qty)
            batch_qty = Decimal(row.batch_qty)
            movement_qty = Decimal(row.movement_qty)
            if balance_qty != batch_qty or balance_qty != movement_qty:
                mismatches.append(
                    {
                        "product_id": row.id,
                        "product_name": row.name,
                        "balance_quantity": balance_qty,
                        "batch_quantity": batch_qty,
                        "movement_quantity": movement_qty,
                        "difference": balance_qty - batch_qty,
                    }
                )
        return {"mismatch_count": len(mismatches), "mismatches": mismatches}

