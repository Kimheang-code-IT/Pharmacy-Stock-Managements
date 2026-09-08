"""Dashboard aggregation service — spec section 2.1.1.

Definitions (aligned with the Finance Report, spec 2.1.10):
- Income        = sum of confirmed sale grand totals in the period.
- Expense       = sum of operating expenses (Add Expense on the Finance
                  Report) in the period — NOT Stock In purchase cost, so the
                  Dashboard and Finance Report always agree.
- Gross Profit  = (Income - sale refunds) - COGS, where COGS is the sold
                  unit cost net of restocked sale returns.
- Damage/Expiry = sum of |quantity_delta| x unit_cost over the matching
                  immutable stock movements in the period.
- Net Income    = Gross Profit - Damage Loss - Expiry Loss - Operating
                  Expenses (finance "net_result"), only when visible.
- Debts         = open remaining balances (all time).
- Sales This Month / Today counts are calendar-based (UTC), independent of
                  the selected reporting period.
- Pending Delivery Notes = notes not yet DELIVERED/CANCELLED (all time).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import user_has_permission
from app.modules.auth.models import User
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.delivery_notes.models import DeliveryNote
from app.modules.pos.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from app.modules.reports.models import Expense
from app.modules.stock.models import (
    Product,
    StockBalance,
    StockMovement,
)
from app.modules.suppliers.models import SupplierDebt


def _day_start(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def resolve_period(*, period: str, start: date | None, end: date | None) -> tuple[date, date]:
    """Supported periods: 7d (default), month, custom(start,end)."""
    today = _today()
    if period == "month":
        first = today.replace(day=1)
        return first, today
    if period == "custom":
        if start is None or end is None:
            raise ValueError("Custom period requires startDate and endDate")
        if start > end:
            start, end = end, start
        return start, end
    return today - timedelta(days=6), today


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------ aggregates

    async def _sales_stats(self, start_at: datetime, end_at: datetime) -> tuple[Decimal, int]:
        """(grand total net of refunds, count) of confirmed sales in [start_at, end_at).

        Income is net of sale-return refunds so Dashboard and Finance Report
        agree on the same period (spec 2.1.10 income statement)."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Sale.grand_total), 0), func.count(Sale.id)).where(
                Sale.sale_date >= start_at, Sale.sale_date < end_at
            )
        )
        total, count = result.one()
        refunds = await self._return_refunds(start_at, end_at)
        return Decimal(total) - refunds, int(count)

    async def _sales_this_month(self) -> tuple[int, Decimal]:
        """Calendar month-to-date (UTC) sales count and amount."""
        month_start = _day_start(_today().replace(day=1))
        amount, count = await self._sales_stats(month_start, _day_start(_today() + timedelta(days=1)))
        return count, amount

    async def _pending_delivery_notes(self) -> int:
        """Delivery notes not yet delivered or cancelled (all time)."""
        result = await self.session.execute(
            select(func.count(DeliveryNote.id)).where(
                DeliveryNote.status.in_(
                    [
                        DeliveryNote.STATUS_DRAFT,
                        DeliveryNote.STATUS_CONFIRMED,
                        DeliveryNote.STATUS_OUT_FOR_DELIVERY,
                    ]
                )
            )
        )
        return int(result.scalar_one())

    async def _operating_expenses(self, start_at: datetime, end_at: datetime) -> Decimal:
        """Operating expenses recorded via Add Expense (Finance Report).
        The Expense KPI/chart intentionally EXCLUDES Stock In purchase cost so
        Dashboard and Finance Report agree (spec 2.1.10)."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.expense_date >= start_at.date(),
                Expense.expense_date < end_at.date(),
            )
        )
        return Decimal(result.scalar_one())

    async def _debt_totals(self) -> tuple[Decimal, Decimal]:
        customer = await self.session.execute(
            select(func.coalesce(func.sum(CustomerDebt.remaining_amount), 0))
        )
        supplier = await self.session.execute(
            select(func.coalesce(func.sum(SupplierDebt.remaining_amount), 0))
        )
        return Decimal(customer.scalar_one()), Decimal(supplier.scalar_one())

    async def _loss_totals(self, movement_type: str, start_at: datetime, end_at: datetime) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(-StockMovement.quantity_delta * StockMovement.unit_cost), 0)).where(
                StockMovement.movement_type == movement_type,
                StockMovement.quantity_delta < 0,
                StockMovement.created_at >= start_at,
                StockMovement.created_at < end_at,
            )
        )
        return Decimal(result.scalar_one())

    async def _return_refunds(self, start_at: datetime, end_at: datetime) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(SaleReturn.refund_amount), 0)).where(
                SaleReturn.return_date >= start_at, SaleReturn.return_date < end_at
            )
        )
        return Decimal(result.scalar_one())

    async def _cogs(self, start_at: datetime, end_at: datetime) -> Decimal:
        """Sold cost for sales in the period, minus cost of restocked returns."""
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
        return Decimal(sold.scalar_one()) - Decimal(restocked.scalar_one())

    # ---------------------------------------------------------------- chart

    async def _chart_series(self, start: date, end: date) -> list[dict]:
        start_at, end_at = _day_start(start), _day_start(end + timedelta(days=1))
        income_rows = await self.session.execute(
            select(
                func.date(Sale.sale_date).label("day"),
                func.coalesce(func.sum(Sale.grand_total), 0),
                func.count(Sale.id),
            )
            .where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
            .group_by(func.date(Sale.sale_date))
        )
        refund_rows = await self.session.execute(
            select(
                func.date(SaleReturn.return_date).label("day"),
                func.coalesce(func.sum(SaleReturn.refund_amount), 0),
            )
            .where(SaleReturn.return_date >= start_at, SaleReturn.return_date < end_at)
            .group_by(func.date(SaleReturn.return_date))
        )
        expense_rows = await self.session.execute(
            select(
                Expense.expense_date.label("day"),
                func.coalesce(func.sum(Expense.amount), 0),
            )
            .where(
                Expense.expense_date >= start_at.date(),
                Expense.expense_date < end_at.date(),
            )
            .group_by(Expense.expense_date)
        )
        income = {row.day: (Decimal(row[1]), int(row[2])) for row in income_rows.all()}
        refunds = {row.day: Decimal(row[1]) for row in refund_rows.all()}
        expense = {row.day: Decimal(row[1]) for row in expense_rows.all()}
        series = []
        day = start
        while day <= end:
            day_income, day_count = income.get(day, (Decimal("0.00"), 0))
            series.append(
                {
                    "date": day,
                    "sales_count": day_count,
                    "income": day_income - refunds.get(day, Decimal("0.00")),
                    "expense": expense.get(day, Decimal("0.00")),
                }
            )
            day += timedelta(days=1)
        return series

    # --------------------------------------------------------------- extras

    async def _stock_alerts(self) -> tuple[int, int]:
        """Low stock: 0 < quantity <= minimum_stock (only for tracked products)."""
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (StockBalance.quantity <= 0, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("out_of_stock"),
                func.coalesce(
                    func.sum(
                        case(
                            ((StockBalance.quantity > 0) & (StockBalance.quantity <= Product.minimum_stock), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("low_stock"),
            )
            .select_from(StockBalance)
            .join(Product, Product.id == StockBalance.product_id)
            .where(Product.status == "ACTIVE", Product.minimum_stock > 0)
        )
        row = result.one()
        return int(row.low_stock), int(row.out_of_stock)

    async def _recent_sales(self) -> list[dict]:
        result = await self.session.execute(
            select(Sale, Customer.name)
            .join(Customer, Customer.id == Sale.customer_id)
            .order_by(Sale.sale_date.desc())
            .limit(5)
        )
        return [
            {
                "id": sale.id,
                "invoice_no": sale.invoice_no,
                "customer_name": name,
                "sale_date": sale.sale_date,
                "grand_total": sale.grand_total,
                "payment_status": sale.payment_status,
            }
            for sale, name in result.all()
        ]

    async def _recent_stock_activity(self) -> list[dict]:
        result = await self.session.execute(
            select(StockMovement, Product.name)
            .join(Product, Product.id == StockMovement.product_id)
            .order_by(StockMovement.created_at.desc())
            .limit(5)
        )
        return [
            {
                "id": movement.id,
                "product_name": name,
                "movement_type": movement.movement_type,
                "quantity_delta": movement.quantity_delta,
                "document_no": movement.document_no,
                "created_at": movement.created_at,
            }
            for movement, name in result.all()
        ]

    async def _top_products(self, start_at: datetime, end_at: datetime) -> list[dict]:
        result = await self.session.execute(
            select(
                SaleItem.product_id,
                Product.name,
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.line_total), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .where(Sale.sale_date >= start_at, Sale.sale_date < end_at)
            .group_by(SaleItem.product_id, Product.name)
            .order_by(func.sum(SaleItem.quantity).desc())
            .limit(5)
        )
        return [
            {
                "product_id": product_id,
                "product_name": name,
                "quantity_sold": Decimal(quantity),
                "sales_amount": Decimal(amount),
            }
            for product_id, name, quantity, amount in result.all()
        ]

    # ----------------------------------------------------------------- main

    async def summary(self, *, period: str, start: date | None, end: date | None, actor: User) -> dict:
        try:
            period_start, period_end = resolve_period(period=period, start=start, end=end)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        start_at = _day_start(period_start)
        end_at = _day_start(period_end + timedelta(days=1))
        profit_visible = user_has_permission(actor, "dashboard.view_profit")

        today_start = _day_start(_today())
        today_end = _day_start(_today() + timedelta(days=1))
        today_sales, today_sales_count = await self._sales_stats(today_start, today_end)
        total_income, _period_sales_count = await self._sales_stats(start_at, end_at)
        total_expense = await self._operating_expenses(start_at, end_at)
        customer_debt, supplier_debt = await self._debt_totals()
        damage_loss = await self._loss_totals("DAMAGE", start_at, end_at)
        expiry_loss = await self._loss_totals("EXPIRE", start_at, end_at)
        month_sales_count, month_sales_amount = await self._sales_this_month()

        gross_profit: Decimal | None = None
        net_income: Decimal | None = None
        if profit_visible:
            # total_income is already net of refunds.
            cogs = await self._cogs(start_at, end_at)
            gross_profit = total_income - cogs
            # Net income = gross profit - losses - operating expenses
            # (finance net_result, spec 2.1.10).
            net_income = gross_profit - damage_loss - expiry_loss - total_expense

        product_count = await self.session.execute(
            select(func.count()).select_from(Product).where(Product.status == "ACTIVE")
        )
        low_stock, out_of_stock = await self._stock_alerts()

        return {
            "period_start": period_start,
            "period_end": period_end,
            "profit_visible": profit_visible,
            "cards": {
                "today_sales": today_sales,
                "today_sales_count": today_sales_count,
                "gross_profit": gross_profit,
                "total_products": int(product_count.scalar_one()),
                "customer_debt": customer_debt,
                "supplier_debt": supplier_debt,
            },
            "chart": await self._chart_series(period_start, period_end),
            "summary": {
                "total_income": total_income,
                "total_expense": total_expense,
                "gross_profit": gross_profit,
                "net_income": net_income,
                "sales_this_month_count": month_sales_count,
                "sales_this_month_amount": month_sales_amount,
                "customer_debt": customer_debt,
                "supplier_debt": supplier_debt,
                "damage_loss": damage_loss,
                "expiry_loss": expiry_loss,
                "pending_delivery_notes_count": await self._pending_delivery_notes(),
            },
            "extras": {
                "low_stock_count": low_stock,
                "out_of_stock_count": out_of_stock,
                "recent_sales": await self._recent_sales(),
                "recent_stock_activity": await self._recent_stock_activity(),
                "top_products": await self._top_products(start_at, end_at),
            },
        }
