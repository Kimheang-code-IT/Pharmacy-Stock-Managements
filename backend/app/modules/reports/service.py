"""Report aggregation service — spec section 2.1.10 (five approved reports).

All reports are read-only aggregations over the authoritative transaction
tables; every metric must reconcile with the underlying movements/payments.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import DateTime, String, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.modules.auth.models import User
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.pos.models import Payment, Sale, SaleItem, SaleReturn, SaleReturnItem
from app.modules.reports.models import Expense
from app.modules.reports.schemas import ExpenseCreate
from app.modules.stock.models import (
    Product,
    StockMovement,
    StockTransaction,
    StockTransactionItem,
)
from app.modules.suppliers.models import Supplier, SupplierDebt
from app.shared.audit.service import record_audit

from app.shared.pagination.params import parse_date_range

Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


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
        return (
            select(
                Sale.id,
                Sale.sale_date,
                Sale.invoice_no,
                Customer.name.label("customer_name"),
                Product.name.label("product_name"),
                Product.sku,
                SaleItem.id.label("sale_item_id"),
                SaleItem.product_id.label("product_id"),
                SaleItem.quantity,
                SaleItem.unit_price,
                SaleItem.discount_amount,
                SaleItem.line_total,
                SaleItem.returned_quantity,
                SaleItem.unit_cost,
                User.full_name.label("cashier_name"),
                Sale.debt_amount,
            )
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .join(Customer, Customer.id == Sale.customer_id)
            .join(User, User.id == Sale.cashier_id)
        )

    @staticmethod
    def _sales_row(row, payment_method: str) -> dict:
        quantity = Decimal(row.quantity)
        returned = Decimal(row.returned_quantity)
        line_total = Decimal(row.line_total)
        unit_cost = Decimal(row.unit_cost)
        net_quantity = quantity - returned
        return_amount = (line_total * returned / quantity).quantize(Q2) if quantity else Q2 * 0
        net_sales = line_total - return_amount
        cost = (unit_cost * net_quantity).quantize(Q2)
        return {
            "sale_id": row.id,
            "sale_item_id": row.sale_item_id,
            "product_id": row.product_id,
            "sale_date": row.sale_date,
            "invoice_no": row.invoice_no,
            "customer_name": row.customer_name,
            "product_name": row.product_name,
            "sku": row.sku,
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
            .join(Product, Product.id == SaleItem.product_id)
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
        filters["limit"] = 100000
        rows, _ = await self.sales_report(**filters)
        return rows

    # ------------------------------------------------------- purchase report

    def _purchase_query(self) -> select:
        return (
            select(
                StockTransaction.id,
                StockTransaction.document_no,
                StockTransaction.transaction_date,
                Supplier.name.label("supplier_name"),
                Product.name.label("product_name"),
                Product.sku,
                StockTransactionItem.id.label("stock_transaction_item_id"),
                StockTransactionItem.product_id.label("product_id"),
                StockTransactionItem.quantity,
                StockTransactionItem.returned_quantity,
                StockTransactionItem.unit_cost,
                StockTransactionItem.line_total,
                StockTransaction.status,
            )
            .select_from(StockTransactionItem)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .join(Product, Product.id == StockTransactionItem.product_id)
            .join(Supplier, Supplier.id == StockTransaction.supplier_id, isouter=True)
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
                    "sku": row.sku,
                    "quantity": quantity,
                    "returned_quantity": returned,
                    "returnable_quantity": (quantity - returned).quantize(Q4),
                    "return_amount": (returned * unit_cost).quantize(Q2),
                    "cost_price": unit_cost,
                    "total_cost": Decimal(row.line_total),
                    "paid_amount": Decimal(row.line_total) - remaining if debt else Decimal(row.line_total),
                    "remaining_debt": remaining,
                    "status": debt.status if debt else "PAID",
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
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Invoice-level customer debt rows (spec 2.1.10 Customer Debt Report).

        The Date column/filter is the invoice (sale) date; every UNPAID,
        PARTIAL and PAID debt document is one row.
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
            return target

        base = (
            select(CustomerDebt, Customer.name, Customer.code, Sale.sale_date)
            .join(Customer, Customer.id == CustomerDebt.customer_id)
            .join(Sale, Sale.id == CustomerDebt.sale_id)
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
                "created_at": debt.created_at,
            }
            for debt, name, code, sale_date in rows.all()
        ]
        return data, int(total)

    async def supplier_debt_report(
        self,
        *,
        q: str | None,
        supplier_id,
        status: str | None,
        start: date | None,
        end: date | None,
        page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Document-level supplier debt rows (spec 2.1.10 Supplier Debt Report).

        The Date column/filter is the stock-in / purchase date; every UNPAID,
        PARTIAL and PAID debt document is one row.
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
            return target

        base = (
            select(SupplierDebt, Supplier.name, Supplier.code, StockTransaction.transaction_date)
            .join(Supplier, Supplier.id == SupplierDebt.supplier_id)
            .join(StockTransaction, StockTransaction.id == SupplierDebt.stock_transaction_id)
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
                "created_at": debt.created_at,
            }
            for debt, name, code, transaction_date in rows.all()
        ]
        return data, int(total)

    # --------------------------------------------------------- finance report

    async def finance_report(self, *, start: date | None, end: date | None) -> dict:
        start_at, end_at = _range(start, end)
        period_start = start_at.date()
        period_end = end_at.date() - timedelta(days=1)

        sales_total = await self.session.execute(
            select(func.coalesce(func.sum(Sale.grand_total), 0)).where(
                Sale.sale_date >= start_at, Sale.sale_date < end_at
            )
        )
        refunds = await self.session.execute(
            select(func.coalesce(func.sum(SaleReturn.refund_amount), 0)).where(
                SaleReturn.return_date >= start_at, SaleReturn.return_date < end_at
            )
        )
        purchase_total = await self.session.execute(
            select(func.coalesce(func.sum(StockTransactionItem.line_total), 0))
            .select_from(StockTransactionItem)
            .join(StockTransaction, StockTransaction.id == StockTransactionItem.stock_transaction_id)
            .where(
                StockTransaction.transaction_type == "STOCK_IN",
                StockTransaction.transaction_date >= start_at,
                StockTransaction.transaction_date < end_at,
            )
        )
        customer_debt = await self.session.execute(
            select(func.coalesce(func.sum(CustomerDebt.remaining_amount), 0))
        )
        supplier_debt = await self.session.execute(
            select(func.coalesce(func.sum(SupplierDebt.remaining_amount), 0))
        )
        operating_expense = await self.session.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.expense_date >= start_at.date(),
                Expense.expense_date < end_at.date(),
            )
        )

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

        sold = await self.session.execute(
            select(func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
        )
        restocked = await self.session.execute(
            select(func.coalesce(func.sum(SaleReturnItem.quantity * SaleItem.unit_cost), 0))
            .join(SaleItem, SaleItem.id == SaleReturnItem.sale_item_id)
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id)
            .where(
                SaleReturnItem.restock.is_(True),
                SaleReturn.return_date >= start_at,
                SaleReturn.return_date < end_at,
            )
        )

        total_sales = Decimal(sales_total.scalar_one()) - Decimal(refunds.scalar_one())
        cogs = Decimal(sold.scalar_one()) - Decimal(restocked.scalar_one())
        gross_profit = total_sales - cogs
        operating_expenses = Decimal(operating_expense.scalar_one())
        # Net Result includes operating expenses (spec 2.1.10 formulas).
        net_result = gross_profit - damage_loss - expiry_loss - operating_expenses

        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_sales": total_sales,
            "total_expense": operating_expenses,
            "total_purchase_cost": Decimal(purchase_total.scalar_one()),
            "total_customer_debt": Decimal(customer_debt.scalar_one()),
            "total_supplier_debt": Decimal(supplier_debt.scalar_one()),
            "cost_of_goods_sold": cogs,
            "stock_damage_loss": damage_loss,
            "stock_expire_loss": expiry_loss,
            "gross_profit": gross_profit,
            "operating_expenses": operating_expenses,
            "net_result": net_result,
        }

    # ------------------------------------------------- finance entries (table)

    def _finance_income_stmt(self) -> select:
        """Income rows derived from confirmed POS sales (never manually added)."""
        latest_method = (
            select(Payment.payment_method)
            .where(Payment.sale_id == Sale.id, Payment.payment_type == "SALE_PAYMENT")
            .order_by(Payment.created_at.desc(), Payment.id)
            .limit(1)
            .correlate(Sale)
            .scalar_subquery()
        )
        return (
            select(
                Sale.id.label("id"),
                Sale.sale_date.label("entry_date"),
                literal("income", type_=String).label("entry_type"),
                Sale.invoice_no.label("reference"),
                literal("Sales", type_=String).label("category"),
                func.coalesce(Customer.name, literal("")).label("description"),
                Sale.grand_total.label("amount"),
                func.coalesce(latest_method, literal("UNPAID")).label("payment_method"),
                func.coalesce(User.full_name, literal("")).label("created_by_name"),
                Sale.created_at.label("created_at"),
            )
            .select_from(Sale)
            .join(Customer, Customer.id == Sale.customer_id)
            .join(User, User.id == Sale.cashier_id)
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
                func.coalesce(Expense.payment_method, literal("")).label("payment_method"),
                func.coalesce(User.full_name, literal("")).label("created_by_name"),
                Expense.created_at.label("created_at"),
            )
            .select_from(Expense)
            .join(User, User.id == Expense.created_by)
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
        union = self._finance_income_stmt().union_all(self._finance_expense_stmt()).subquery()

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
        """Record one operating expense (Finance Report only) with audit."""
        amount = payload.amount.quantize(Q2)
        if amount <= 0:
            raise ValidationError("Expense amount must be greater than zero")
        expense = Expense(
            expense_date=payload.date,
            category=payload.category.strip(),
            description=(payload.description or "").strip() or None,
            reference=(payload.reference or "").strip() or None,
            amount=amount,
            payment_method=payload.payment_method,
            created_by=actor.id,
        )
        self.session.add(expense)
        await self.session.flush()
        await record_audit(
            self.session,
            action="CREATE",
            module="reports",
            user_id=actor.id,
            entity_type="Expense",
            entity_id=expense.id,
            new_values={
                "expense_date": payload.date.isoformat(),
                "category": expense.category,
                "description": expense.description,
                "amount": str(amount),
                "payment_method": expense.payment_method,
            },
        )
        await self.session.commit()
        return expense
