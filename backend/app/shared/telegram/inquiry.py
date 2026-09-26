"""View-only Telegram stock inquiry (spec sections 3.6 / 3.6.1).

Read-only query adapters used by the `telegram-bot` Compose process. Every
function here only SELECTs from the canonical tables (products, stock
balances, stock movements, sales, system_settings) — the same single source
of truth used by the API. Nothing in this module writes, mutates, or commits;
the bot process must never issue mutating SQL.

Access model:
- the `telegram.stock_inquiry_enabled` setting must be true, and
- the chat must belong to an ACTIVE user whose `telegram_chat_id` matches.
Unlinked or disabled chats receive an instruction only — never business data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.administration.service import get_setting_value
from app.modules.auth.models import User
from app.modules.pos.models import Sale
from app.modules.stock.models import Product, StockBalance
from app.modules.telegram.repository import ExpiryAlertRepository
from app.modules.uoms.models import UOM

PAGE_SIZE = 15
MAX_MESSAGE_CHARS = 3500

# --------------------------------------------------------------- bot replies

VIEW_ONLY_REPLY = "View only"
UNLINKED_REPLY = (
    "Your Telegram chat is not linked to a Stock & POS user.\n"
    "Ask an administrator to set this Chat ID in the app "
    "(Administration > Users > your profile, Telegram Chat ID):\n"
    "{chat_id}"
)
DISABLED_REPLY = "Stock inquiry is currently disabled in the shop settings."
# Same authorization the HTTP stock API enforces: a linked chat is not enough,
# the account must hold `stock.view`.
NO_PERMISSION_REPLY = (
    "Your account does not have permission to view stock. "
    "Ask an administrator to grant the Stock View permission."
)

# --------------------------------------------------------- callback routing
#
# Whitelist of read-only callback payloads. Anything else (including crafted
# write-shaped payloads such as "stock:adjust" or "sale:create") is refused
# with the VIEW_ONLY_REPLY and ignored.

CB_MENU = "menu"
CB_HELP = "help"
CB_TOOL_PREFIX = "tool:"  # tool:<tool>
CB_PAGE_PREFIX = "page:"  # page:<tool>:<period|->:<n>

TOOLS = ("current_stock", "low_stock", "expiring", "sales")
PERIODS = ("today", "7d", "month")


@dataclass(frozen=True)
class InquiryAction:
    """A parsed, whitelisted read-only bot action."""

    tool: str
    period: str | None = None
    page: int = 1


def route_callback(data: str | None) -> InquiryAction | None:
    """Map a callback payload to a read-only action.

    Returns None for anything that is not a known read-only callback (write
    attempts, unknown tools, malformed payloads). Callers must reply
    "View only" and ignore those.
    """
    if not data:
        return None
    if data == CB_MENU:
        return InquiryAction(tool="menu")
    if data == CB_HELP:
        return InquiryAction(tool="help")
    if data.startswith(CB_TOOL_PREFIX):
        tool = data[len(CB_TOOL_PREFIX) :]
        if tool in TOOLS:
            return InquiryAction(tool=tool)
        return None
    if data.startswith(CB_PAGE_PREFIX):
        parts = data[len(CB_PAGE_PREFIX) :].split(":")
        if len(parts) != 3 or parts[0] not in TOOLS:
            return None
        period = None if parts[1] == "-" else parts[1]
        if period is not None and period not in PERIODS:
            return None
        if not parts[2].isdigit():
            return None
        page = int(parts[2])
        if not 1 <= page <= 9999:
            return None
        return InquiryAction(tool=parts[0], period=period, page=page)
    return None


# ------------------------------------------------------------------- access


async def resolve_access(session: AsyncSession, chat_id: str) -> tuple[User | None, str | None]:
    """Gate every inquiry: setting enabled + verified chat link.

    Returns (user, None) when allowed, or (None, reply_text) with an
    instruction that contains no business data.
    """
    enabled = await get_setting_value(session, "telegram", "stock_inquiry_enabled", True)
    if not enabled:
        return None, DISABLED_REPLY
    result = await session.execute(
        select(User)
        # Eager-load the role so permission checks (summary sections) never
        # trigger an async lazy-load outside the session's await context.
        .options(selectinload(User.role_ref))
        .where(
            User.telegram_chat_id.is_not(None),
            User.telegram_chat_id != "",
            User.telegram_chat_id == str(chat_id),
            User.telegram_verified.is_(True),
            User.status == "ACTIVE",
        )
    )
    user = result.scalars().first()
    if user is None:
        return None, UNLINKED_REPLY.format(chat_id=chat_id)
    return user, None


# Per-tool role requirements — the SAME permissions the authenticated HTTP
# endpoints enforce. A verified chat is not enough to read stock/sales data.
TOOL_PERMISSIONS: dict[str, str] = {
    "current_stock": "stock.view",
    "low_stock": "stock.view",
    "expiring": "stock.view",
    "sales": "report.sales",
}


def check_tool_permission(user, tool: str) -> bool:
    """True when `user` may run `tool` (mirrors the HTTP authorization)."""
    required = TOOL_PERMISSIONS.get(tool)
    if required is None:
        return False
    from app.core.permissions import user_has_permission

    return user_has_permission(user, required)


# ------------------------------------------------------------------ periods


def period_bounds(period: str) -> tuple[datetime, datetime]:
    """UTC [start, end) window for Today / Last 7 days / This month."""
    today = datetime.now(timezone.utc).date()
    if period == "today":
        start = today
    elif period == "7d":
        start = today - timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
    else:
        raise ValueError(f"Unknown period '{period}'")
    end = today
    day_start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    day_end = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
    return day_start, day_end


# -------------------------------------------------------------------- tools


async def _uom_codes(session: AsyncSession, product_ids: list) -> dict:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(Product.uom_id, UOM.code).join(UOM, UOM.id == Product.uom_id).where(Product.id.in_(product_ids))
    )
    return dict(rows.all())


async def current_stock_rows(session: AsyncSession, page: int, page_size: int = PAGE_SIZE):
    """Paged current stock (product, qty, UOM) from the canonical balance."""
    base = (
        select(Product.name, Product.barcode, StockBalance.quantity, UOM.code.label("uom"))
        .select_from(Product)
        .join(StockBalance, StockBalance.product_id == Product.id)
        .join(UOM, UOM.id == Product.uom_id)
        .where(Product.status == "ACTIVE")
    )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = await session.execute(
        base.order_by(Product.name, Product.barcode)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [dict(row._mapping) for row in rows.all()], int(total)


async def low_stock_rows(session: AsyncSession, page: int, page_size: int = PAGE_SIZE):
    """Paged low/out-of-stock products.

    Same rule as the dashboard read model: 0 < quantity <= minimum_stock is
    LOW; quantity <= 0 is OUT.
    """
    base = (
        select(Product.name, Product.barcode, StockBalance.quantity, Product.minimum_stock, UOM.code.label("uom"))
        .select_from(Product)
        .join(StockBalance, StockBalance.product_id == Product.id)
        .join(UOM, UOM.id == Product.uom_id)
        .where(Product.status == "ACTIVE", Product.minimum_stock > 0, StockBalance.quantity <= Product.minimum_stock)
    )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = await session.execute(
        base.order_by(StockBalance.quantity, Product.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [dict(row._mapping) for row in rows.all()], int(total)


async def expiring_rows(session: AsyncSession, page: int, page_size: int = PAGE_SIZE):
    """Paged lots expiring inside the Alert 1 settings window.

    Windows come from the persisted settings `stock.expiry_alert_1_days` and
    `stock.expiry_alert_2_days` (spec section 3.6). Lot remaining quantities
    reuse the canonical `ExpiryAlertRepository.expiring_lots()` read model
    (immutable stock movements) — the same single inventory truth the expiry
    alert job uses, not a second implementation.
    """
    alert1 = int(await get_setting_value(session, "stock", "expiry_alert_1_days", 90))
    alert2 = int(await get_setting_value(session, "stock", "expiry_alert_2_days", 7))
    today = datetime.now(timezone.utc).date()
    cutoff1 = today + timedelta(days=alert1)
    cutoff2 = today + timedelta(days=alert2)
    lots = await ExpiryAlertRepository(session).expiring_lots()
    lots = [lot for lot in lots if today <= lot["expiry_date"] <= cutoff1]
    lots.sort(key=lambda lot: (lot["expiry_date"], lot["product_name"]))
    total = len(lots)
    start = (page - 1) * page_size
    rows = lots[start : start + page_size]
    uom_by_product = await _uom_codes(session, [lot["product_id"] for lot in rows])
    return (
        [lot | {"cutoff2": cutoff2, "uom": uom_by_product.get(lot["product_id"], "")} for lot in rows],
        total,
        alert1,
        alert2,
    )


async def sales_summary(session: AsyncSession, period: str) -> dict:
    """Period sales totals per document currency: invoices, gross, paid, debt.

    USD and KHR are reported separately and never summed together.
    """
    start, end = period_bounds(period)
    result = await session.execute(
        select(
            Sale.currency,
            func.count(),
            func.coalesce(func.sum(Sale.grand_total), 0),
            func.coalesce(func.sum(Sale.paid_amount), 0),
            func.coalesce(func.sum(Sale.debt_amount), 0),
        )
        .where(
            Sale.sale_date >= start,
            Sale.sale_date < end,
            Sale.sale_status.in_(("COMPLETED", "PARTIAL_RETURN")),
        )
        .group_by(Sale.currency)
    )
    buckets = []
    invoices = 0
    for currency, count, gross, paid, debt in result.all():
        invoices += int(count)
        buckets.append(
            {
                "currency": str(currency or "USD").upper(),
                "invoices": int(count),
                "gross": Decimal(gross),
                "paid": Decimal(paid),
                "debt": Decimal(debt),
            }
        )
    return {"period": period, "invoices": invoices, "buckets": buckets}


# ---------------------------------------------------------------- formatting


def _fmt_qty(value) -> str:
    """Trim trailing zeros without scientific notation (10.0000 → 10)."""
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (ValueError, ArithmeticError):
        return str(value if value is not None else "-")


def _money(amount, currency="USD") -> str:
    """Document-currency amount, e.g. ``USD 13.00`` (never sums currencies)."""
    try:
        value = f"{Decimal(str(amount if amount is not None else 0)):.2f}"
    except (ValueError, ArithmeticError):
        value = str(amount)
    return f"{str(currency or 'USD').upper()} {value}"


def render_page(
    title: str,
    lines: list[str],
    page: int,
    total: int,
    page_size: int = PAGE_SIZE,
    *,
    title_only: bool = False,
) -> tuple[str, int]:
    """Render one compact page. Returns (text, total_pages)."""
    total_pages = max(1, -(-total // page_size))
    page = min(max(1, page), total_pages)
    body = "\n".join(lines[: MAX_MESSAGE_CHARS]) if lines else "(no data)"
    if title_only:
        text = f"{title}\n\n{body}"
    else:
        header = f"{title} (page {page}/{total_pages}, {total} rows)"
        text = f"{header}\n{'-' * len(header)}\n{body}"
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 3] + "..."
    return text, total_pages


async def run_tool(session: AsyncSession, action: InquiryAction, *, user=None) -> tuple[str, int]:
    """Execute a whitelisted read-only tool. Returns (text, total_pages).

    When `user` is supplied the tool's role permission is enforced (the same
    authorization as the HTTP endpoints); callers without it are refused.
    """
    if user is not None and not check_tool_permission(user, action.tool):
        raise PermissionError(NO_PERMISSION_REPLY)
    page = max(1, action.page)
    if action.tool == "current_stock":
        rows, total = await current_stock_rows(session, page)
        lines = [f"Total Current Stock: {total}", ""]
        lines.extend(f"- {r['name']} : {_fmt_qty(r['quantity'])} {r['uom']}".rstrip() for r in rows)
        return render_page("🧾 Current Stock", lines, page, total, title_only=True)
    if action.tool == "low_stock":
        rows, total = await low_stock_rows(session, page)
        lines = [f"Total Low : {total}", ""]
        lines.extend(f"- {r['name']} : {_fmt_qty(r['quantity'])} {r['uom']}".rstrip() for r in rows)
        return render_page("🪫 Low Stock", lines, page, total, title_only=True)
    if action.tool == "expiring":
        rows, total, *_ = await expiring_rows(session, page)
        alert1_lines: list[str] = []
        alert2_lines: list[str] = []
        for lot in rows:
            line = (
                f"- {lot['product_name']} : {lot['expiry_date'].isoformat()} "
                f": batch: {lot['batch_no'] or '-'}"
            )
            if lot["expiry_date"] <= lot["cutoff2"]:
                alert2_lines.append(line)
            else:
                alert1_lines.append(line)
        lines = [f"Total Expiring : {total}"]
        if alert1_lines:
            lines.extend(["", "[ALERT 1]", *alert1_lines])
        if alert2_lines:
            lines.extend(["", "[ALERT 2]", *alert2_lines])
        return render_page("⏱️ Expiring Soon", lines, page, total, title_only=True)
    if action.tool == "sales":
        if not action.period:
            raise ValueError("Sales summary requires a period")
        summary = await sales_summary(session, action.period)
        label = {"today": "Today", "7d": "Last 7 days", "month": "This month"}[action.period]
        lines = [f"Invoices: {summary['invoices']}"]
        buckets = summary["buckets"] or [
            {"currency": "USD", "gross": Decimal("0"), "paid": Decimal("0"), "debt": Decimal("0")}
        ]
        for index, bucket in enumerate(buckets):
            if len(buckets) > 1:
                if index:
                    lines.append("")
                lines.append(f"{bucket['currency']}:")
            lines.append(f"Gross sales: {_money(bucket['gross'], bucket['currency'])}")
            lines.append(f"Paid: {_money(bucket['paid'], bucket['currency'])}")
            lines.append(f"Debt: {_money(bucket['debt'], bucket['currency'])}")
        return render_page(f"Sales Summary — {label}", lines, 1, 1, title_only=True)
    raise ValueError(f"Unknown tool '{action.tool}'")


HELP_TEXT = (
    "Stock & POS inquiry bot (view only).\n"
    "Use the buttons below: Summary, Current Stock, Low Stock, Expiring Soon, Help.\n"
    "Summary asks for a period (Today / Last 7 Days / This Month / Custom Date Range).\n"
    "Custom Date Range: send a start and end date as YYYY-MM-DD (e.g. 2026-09-30).\n"
    "Long stock lists are paginated — use Previous / Next.\n"
    "This bot cannot create, edit, or delete anything."
)
