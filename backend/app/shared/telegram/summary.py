"""On-demand Telegram period summary (read-only).

The bot's Summary tool asks for a period (Today / Last 7 Days / This Month /
custom range) and replies with one compact message covering sales, purchases,
operating expenses, returns and deliveries for that period.

Design rules:

- All calendar boundaries are resolved in the configured **shop timezone**
  (`system.timezone`), then converted to a UTC ``[start, end)`` window for the
  database queries — never UTC calendar dates.
- Money is ``Decimal`` and every amount stays in its **document currency**;
  USD and KHR totals are reported separately and never added together.
- Every section is gated by the caller's role permission
  (`report.sales`, `report.purchase`, `report.finance`, `delivery.view`);
  a user who lacks a permission simply does not see that section.
- Read-only: this module only issues SELECTs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import effective_permissions, user_has_permission
from app.modules.administration.service import get_setting_value
from app.modules.auth.models import User
from app.modules.delivery.models import DeliveryNote
from app.modules.pos.models import Sale, SaleReturn
from app.modules.reports.models import Expense
from app.modules.stock.models import (
    PurchaseReturn,
    StockTransaction,
    StockTransactionItem,
)

Q2 = Decimal("0.01")

# ------------------------------------------------------------------ constants

PERIOD_TODAY = "today"
PERIOD_7D = "7d"
PERIOD_MONTH = "month"
PERIOD_CUSTOM = "custom"
PERIODS = (PERIOD_TODAY, PERIOD_7D, PERIOD_MONTH, PERIOD_CUSTOM)

DEFAULT_TIMEZONE = "UTC"
# Hard cap so a crafted custom range can never scan the whole ledger.
DEFAULT_MAX_CUSTOM_RANGE_DAYS = 366

PERM_SALES = "report.sales"
PERM_PURCHASE = "report.purchase"
PERM_FINANCE = "report.finance"
PERM_DELIVERY = "delivery.view"

# Sales documents that count as business (a fully voided sale is excluded).
_SALE_STATUSES = ("COMPLETED", "PARTIAL_RETURN")

# Delivery status vocabulary (app.modules.delivery.models.DeliveryNote).
DELIVERY_DELIVERED = "DELIVERED"
DELIVERY_UNFINISHED = ("PENDING", "PREPARING", "OUT_FOR_DELIVERY", "PARTIALLY_DELIVERED")
DELIVERY_TERMINAL = ("FAILED", "RETURNED")

MAX_MESSAGE_CHARS = 3500


# ------------------------------------------------------------------ timezone


def shop_timezone(name: str | None) -> ZoneInfo:
    """Resolve a configured timezone name, falling back to UTC."""
    try:
        return ZoneInfo(str(name or "").strip() or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_today(tz: ZoneInfo) -> date:
    """Shop-local calendar date (never the UTC date)."""
    return datetime.now(tz).date()


def resolve_period(period: str, *, tz: ZoneInfo, today: date | None = None) -> tuple[date, date]:
    """Inclusive local ``(start, end)`` dates for a fixed period.

    - Today: today.
    - Last 7 Days: today plus the previous six local calendar days.
    - This Month: the first day of the current local month through today.
    """
    current = today or local_today(tz)
    if period == PERIOD_TODAY:
        return current, current
    if period == PERIOD_7D:
        return current - timedelta(days=6), current
    if period == PERIOD_MONTH:
        return current.replace(day=1), current
    raise ValueError(f"Unknown period '{period}'")


def utc_window(local_start: date, local_end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Convert inclusive local dates to a half-open UTC ``[start, end)`` window."""
    start = datetime.combine(local_start, time.min, tzinfo=tz)
    end = datetime.combine(local_end + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parse_iso_date(text: str | None) -> date | None:
    """Strictly parse ``YYYY-MM-DD``; returns None for anything else."""
    value = str(text or "").strip()
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return None
    if not (value[:4].isdigit() and value[5:7].isdigit() and value[8:10].isdigit()):
        return None
    try:
        return date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def custom_range_error(
    start: date | None,
    end: date | None,
    *,
    max_days: int = DEFAULT_MAX_CUSTOM_RANGE_DAYS,
) -> str | None:
    """Human message when a custom range is invalid, else None."""
    if start is None or end is None:
        return "Please provide both a start and an end date in YYYY-MM-DD format."
    if start > end:
        return "The start date must be on or before the end date."
    span = (end - start).days + 1
    if span > max_days:
        return f"The range is too long ({span} days). Please choose {max_days} days or fewer."
    return None


async def max_custom_range_days(session: AsyncSession) -> int:
    """Configured custom-range cap (`telegram.summary_max_range_days`)."""
    raw = await get_setting_value(
        session, "telegram", "summary_max_range_days", DEFAULT_MAX_CUSTOM_RANGE_DAYS
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_CUSTOM_RANGE_DAYS
    return value if value >= 1 else DEFAULT_MAX_CUSTOM_RANGE_DAYS


# --------------------------------------------------------------- aggregations


def _empty_totals() -> dict[str, Decimal]:
    return {"USD": Decimal("0"), "KHR": Decimal("0")}


def _accumulate(totals: dict[str, Decimal], currency, amount) -> None:
    key = str(currency or "USD").upper()
    if key not in totals:
        totals[key] = Decimal("0")
    totals[key] += Decimal(amount or 0)


async def _currency_count_totals(session, stmt) -> dict:
    """Run a (currency, count, amount) grouped statement into a bucket dict."""
    totals = _empty_totals()
    count = 0
    for currency, row_count, amount in (await session.execute(stmt)).all():
        count += int(row_count or 0)
        _accumulate(totals, currency, amount)
    return {"count": count, "totals": totals}


async def _sales_summary(session, start: datetime, end: datetime) -> dict:
    stmt = (
        select(
            Sale.currency,
            func.count(),
            func.coalesce(func.sum(Sale.grand_total), 0),
        )
        .where(
            Sale.sale_date >= start,
            Sale.sale_date < end,
            Sale.sale_status.in_(_SALE_STATUSES),
        )
        .group_by(Sale.currency)
    )
    return await _currency_count_totals(session, stmt)


async def _sale_returns_summary(session, start: datetime, end: datetime) -> dict:
    stmt = (
        select(
            SaleReturn.currency,
            func.count(),
            func.coalesce(func.sum(SaleReturn.refund_amount), 0),
        )
        .where(
            SaleReturn.return_date >= start,
            SaleReturn.return_date < end,
            SaleReturn.status != "VOID",
        )
        .group_by(SaleReturn.currency)
    )
    return await _currency_count_totals(session, stmt)


async def _purchases_summary(session, start: datetime, end: datetime) -> dict:
    """Purchases use the purchase report's document-total formula:
    sum(line_total) − discount + tax, grouped by document currency."""
    items_subtotal = (
        select(
            StockTransactionItem.stock_transaction_id.label("tx_id"),
            func.coalesce(func.sum(StockTransactionItem.line_total), 0).label("subtotal"),
        )
        .group_by(StockTransactionItem.stock_transaction_id)
        .subquery()
    )
    stmt = (
        select(
            StockTransaction.currency,
            func.count(),
            func.coalesce(
                func.sum(
                    items_subtotal.c.subtotal
                    - StockTransaction.discount_amount
                    + StockTransaction.tax_amount
                ),
                0,
            ),
        )
        .join(items_subtotal, items_subtotal.c.tx_id == StockTransaction.id)
        .where(
            StockTransaction.transaction_type == "STOCK_IN",
            StockTransaction.transaction_date >= start,
            StockTransaction.transaction_date < end,
        )
        .group_by(StockTransaction.currency)
    )
    return await _currency_count_totals(session, stmt)


async def _purchase_returns_summary(session, start: datetime, end: datetime) -> dict:
    """Purchase returns by return date; currency from the linked purchase."""
    stmt = (
        select(
            StockTransaction.currency,
            func.count(),
            func.coalesce(func.sum(PurchaseReturn.refund_amount), 0),
        )
        .select_from(PurchaseReturn)
        .join(StockTransaction, StockTransaction.id == PurchaseReturn.stock_transaction_id)
        .where(
            PurchaseReturn.return_date >= start,
            PurchaseReturn.return_date < end,
        )
        .group_by(StockTransaction.currency)
    )
    return await _currency_count_totals(session, stmt)


async def _expenses_summary(session, local_start: date, local_end: date) -> dict:
    """Operating expenses only (POSTED), by local expense date.

    Supplier payments are NOT operating expenses and are never counted here.
    """
    stmt = (
        select(
            Expense.currency,
            func.count(),
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .where(
            Expense.status == "POSTED",
            Expense.expense_date >= local_start,
            Expense.expense_date <= local_end,
        )
        .group_by(Expense.currency)
    )
    return await _currency_count_totals(session, stmt)


def classify_delivery_counts(counts: dict[str, int]) -> dict:
    """Classify delivery-status counts consistently.

    DELIVERED counts as completed; active unfinished statuses count as not
    completed; FAILED/RETURNED (cancelled) are reported separately so they are
    never mistaken for success or pending work. Unknown statuses are surfaced
    under ``other`` rather than silently folded into a bucket.
    """
    completed = int(counts.get(DELIVERY_DELIVERED, 0))
    not_completed = sum(int(counts.get(status, 0)) for status in DELIVERY_UNFINISHED)
    terminal = {status: int(counts.get(status, 0)) for status in DELIVERY_TERMINAL}
    known = (DELIVERY_DELIVERED, *DELIVERY_UNFINISHED, *DELIVERY_TERMINAL)
    return {
        "completed": completed,
        "not_completed": not_completed,
        "terminal": terminal,
        "other": {status: int(count) for status, count in counts.items() if status not in known},
    }


async def _deliveries_summary(session, start: datetime, end: datetime) -> dict:
    """Delivery notes CREATED in the period, classified by current status."""
    rows = await session.execute(
        select(DeliveryNote.status, func.count())
        .where(DeliveryNote.created_at >= start, DeliveryNote.created_at < end)
        .group_by(DeliveryNote.status)
    )
    counts = {str(status): int(count) for status, count in rows.all()}
    return classify_delivery_counts(counts)


async def period_summary(
    session: AsyncSession,
    *,
    utc_start: datetime,
    utc_end: datetime,
    local_start: date,
    local_end: date,
    user: User,
) -> dict:
    """Read-only summary for ``[utc_start, utc_end)`` / the local date range.

    Sections the user lacks permission for are omitted entirely (the message
    then hides them). Money stays in separate USD/KHR buckets.
    """
    summary: dict = {
        "period_start": local_start.isoformat(),
        "period_end": local_end.isoformat(),
    }
    if user_has_permission(user, PERM_SALES):
        summary["sales"] = await _sales_summary(session, utc_start, utc_end)
        summary["sale_returns"] = await _sale_returns_summary(session, utc_start, utc_end)
    if user_has_permission(user, PERM_PURCHASE):
        summary["purchases"] = await _purchases_summary(session, utc_start, utc_end)
        summary["purchase_returns"] = await _purchase_returns_summary(session, utc_start, utc_end)
    if user_has_permission(user, PERM_FINANCE):
        summary["expenses"] = await _expenses_summary(session, local_start, local_end)
    if user_has_permission(user, PERM_DELIVERY):
        summary["deliveries"] = await _deliveries_summary(session, utc_start, utc_end)
    return summary


def visible_sections(summary: dict) -> list[str]:
    return [key for key in ("sales", "purchases", "expenses", "deliveries") if key in summary]


# ---------------------------------------------------------------- formatting

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Summary",
        "period": "Period",
        "sales": "Sales",
        "invoices": "invoices",
        "purchases": "Purchases",
        "documents": "documents",
        "expenses": "Expenses",
        "entries": "entries",
        "returns": "Returns",
        "sale_returns": "Sale returns",
        "purchase_returns": "Purchase returns",
        "combined": "Total return documents",
        "delivered": "Deliveries completed",
        "not_delivered": "Deliveries not completed",
        "failed": "Failed",
        "returned": "Cancelled",
        "no_sections": "No summary sections are available for your role.",
    },
    "km": {
        "title": "សេចក្តីសង្ខេប",
        "period": "រយៈពេល",
        "sales": "ការលក់",
        "invoices": "វិក្កយបត្រ",
        "purchases": "ការទិញ",
        "documents": "ឯកសារ",
        "expenses": "ចំណាយ",
        "entries": "កំណត់ត្រា",
        "returns": "ការត្រឡប់",
        "sale_returns": "ត្រឡប់ការលក់",
        "purchase_returns": "ត្រឡប់ការទិញ",
        "combined": "ឯកសារត្រឡប់សរុប",
        "delivered": "ការដឹកជញ្ជូនបានសម្រេច",
        "not_delivered": "ការដឹកជញ្ជូនមិនបានសម្រេច",
        "failed": "បរាជ័យ",
        "returned": "បានបោះបង់",
        "no_sections": "មិនមានផ្នែកសេចក្តីសង្ខេបសម្រាប់តួនាទីរបស់អ្នកទេ។",
    },
}


def _language(lang: str | None) -> dict[str, str]:
    return _LABELS.get("km" if str(lang or "").lower() == "km" else "en", _LABELS["en"])


def _money_totals(totals: dict[str, Decimal]) -> str:
    parts = [
        f"{currency} {Decimal(amount or 0).quantize(Q2)}"
        for currency, amount in totals.items()
        if Decimal(amount or 0) != 0
    ]
    return " / ".join(parts) if parts else "0.00"


def render_summary(summary: dict, *, lang: str = "en") -> str:
    """Compact plain-text summary (no markup, safe for any Telegram client)."""
    labels = _language(lang)
    lines = [
        f"{labels['title']}",
        f"{labels['period']}: {summary.get('period_start', '-')} .. {summary.get('period_end', '-')}",
        "",
    ]

    if "sales" in summary:
        sales = summary["sales"]
        lines.append(f"{labels['sales']}: {sales['count']} {labels['invoices']} — {_money_totals(sales['totals'])}")

    if "purchases" in summary:
        purchases = summary["purchases"]
        lines.append(f"{labels['purchases']}: {purchases['count']} {labels['documents']} — {_money_totals(purchases['totals'])}")

    if "expenses" in summary:
        expenses = summary["expenses"]
        lines.append(f"{labels['expenses']}: {expenses['count']} {labels['entries']} — {_money_totals(expenses['totals'])}")

    if "sale_returns" in summary or "purchase_returns" in summary:
        lines.append(f"{labels['returns']}:")
        if "sale_returns" in summary:
            sale_returns = summary["sale_returns"]
            lines.append(
                f"  {labels['sale_returns']}: {sale_returns['count']} — {_money_totals(sale_returns['totals'])}"
            )
        if "purchase_returns" in summary:
            purchase_returns = summary["purchase_returns"]
            lines.append(
                f"  {labels['purchase_returns']}: {purchase_returns['count']} — {_money_totals(purchase_returns['totals'])}"
            )
        if "sale_returns" in summary and "purchase_returns" in summary:
            combined = summary["sale_returns"]["count"] + summary["purchase_returns"]["count"]
            if combined:
                lines.append(f"  {labels['combined']}: {combined}")

    if "deliveries" in summary:
        deliveries = summary["deliveries"]
        lines.append(f"{labels['delivered']}: {deliveries['completed']}")
        lines.append(f"{labels['not_delivered']}: {deliveries['not_completed']}")
        terminal = deliveries.get("terminal") or {}
        if terminal.get("FAILED"):
            lines.append(f"  {labels['failed']}: {terminal['FAILED']}")
        if terminal.get("RETURNED"):
            lines.append(f"  {labels['returned']}: {terminal['RETURNED']}")

    if not visible_sections(summary):
        lines.append(labels["no_sections"])

    text = "\n".join(lines).strip()
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 3] + "..."
    return text


# ------------------------------------------------------- conversation state


@dataclass
class _CustomRange:
    step: str  # "start" | "end"
    start: date | None = None


@dataclass
class SummaryConversation:
    """Per-chat conversation state (custom date entry + stock pagination).

    Kept in memory in the bot process. It holds only the *shape* of the
    in-progress interaction (never business data), and every inbound message
    still passes the access gate, so a stale state can never leak anything.
    """

    _custom: dict[str, _CustomRange] = field(default_factory=dict)
    _pager: dict[str, dict] = field(default_factory=dict)

    # -- custom range ------------------------------------------------------
    def begin_custom(self, chat_id: str) -> None:
        self._custom[str(chat_id)] = _CustomRange(step="start")

    def custom_step(self, chat_id: str) -> str | None:
        state = self._custom.get(str(chat_id))
        return state.step if state else None

    def custom_start(self, chat_id: str) -> date | None:
        state = self._custom.get(str(chat_id))
        return state.start if state else None

    def set_custom_start(self, chat_id: str, start: date) -> None:
        self._custom[str(chat_id)] = _CustomRange(step="end", start=start)

    def cancel_custom(self, chat_id: str) -> None:
        self._custom.pop(str(chat_id), None)

    # -- stock pagination --------------------------------------------------
    def set_pager(self, chat_id: str, tool: str, page: int) -> None:
        self._pager[str(chat_id)] = {"tool": tool, "page": max(1, int(page))}

    def pager(self, chat_id: str) -> dict | None:
        return self._pager.get(str(chat_id))

    def clear_pager(self, chat_id: str) -> None:
        self._pager.pop(str(chat_id), None)

    # -- global ------------------------------------------------------------
    def reset(self, chat_id: str) -> None:
        self.cancel_custom(chat_id)
        self.clear_pager(chat_id)


# Explicit re-export so callers can pre-load permissions if needed.
__all__ = [
    "DEFAULT_MAX_CUSTOM_RANGE_DAYS",
    "PERIODS",
    "PERIOD_7D",
    "PERIOD_CUSTOM",
    "PERIOD_MONTH",
    "PERIOD_TODAY",
    "SummaryConversation",
    "classify_delivery_counts",
    "custom_range_error",
    "effective_permissions",
    "local_today",
    "max_custom_range_days",
    "parse_iso_date",
    "period_summary",
    "render_summary",
    "resolve_period",
    "shop_timezone",
    "utc_window",
    "visible_sections",
]
