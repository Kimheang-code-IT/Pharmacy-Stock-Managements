"""Canonical Telegram notification service (spec §3.6).

One service owns every business notification: expiry alerts, sale
notifications, purchase (Stock In) notifications, the daily summary and the
test message. Rules:

- Every notification type is gated by a Settings toggle
  (telegram.*_enabled) read per send — changing a toggle takes effect
  immediately.
- Delivery failures NEVER raise into business flows: callers invoke this
  module after their transaction has committed, and every send swallows and
  logs errors.
- No invoice/receipt files or PDFs are ever sent — plain text only.
- Recipients are every ACTIVE user with a verified telegram_chat_id.
"""

from __future__ import annotations

import html
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.service import get_setting_value
from app.modules.auth.models import User

logger = logging.getLogger("stock_pos.telegram")

Sender = callable

# ------------------------------------------------------- bilingual text tables
#
# Receipt-style notification cards (Telegram HTML). The language is the
# `telegram.notification_language` setting (English by default) so an operator
# can switch every bot message to Khmer from Settings.

_EMOJI = {
    "sale": "🧾",
    "purchase": "📥",
    "payment": "💵",
    "supplier_payment": "💸",
    "daily": "📊",
    "test": "✅",
    "backup": "💾",
}

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "sale": "New Checkout Completed",
        "purchase": "Stock In Received",
        "payment": "Debt Payment Received",
        "supplier_payment": "Supplier Payment",
        "daily": "Daily Summary",
        "test": "Test Notification",
        "invoice_id": "Invoice ID",
        "document": "Document",
        "customer": "Customer",
        "supplier": "Supplier",
        "phone": "Phone",
        "payment_method": "Payment",
        "delivery": "Delivery",
        "products": "Products",
        "subtotal": "Subtotal",
        "delivery_fee": "Delivery Fee",
        "discount": "Discount",
        "tax": "Tax",
        "total": "Total",
        "paid": "Paid",
        "debt": "Debt",
        "remaining": "Remaining debt",
        "date": "Date",
        "by": "By",
        "walkin": "Walk-in Customer",
        "sales": "Sales",
        "purchases": "Purchases",
        "customer_debt": "Customer debt outstanding",
        "supplier_debt": "Supplier debt outstanding",
        "delivered": "Delivered",
        "pending_deliveries": "Pending deliveries",
        "out_of_stock": "Out-of-stock products",
        "backup": "Google Sheets Backup",
        "backup_ok": "Backup completed",
        "backup_partial": "Backup completed with errors",
        "backup_failed": "Backup failed",
        "backup_tables": "Tables",
        "backup_new": "New rows",
        "backup_updated": "Updated rows",
        "backup_skipped": "Skipped",
        "backup_failed_tables": "Failed tables",
        "backup_sheet": "Google Sheet",
    },
    "km": {
        "sale": "ការលក់បានសម្រេច",
        "purchase": "ទទួលស្តុកចូល",
        "payment": "ទទួលប្រាក់បង់បំណុល",
        "supplier_payment": "ការបង់ប្រាក់ទៅអ្នកផ្គត់ផ្គង់",
        "daily": "សេចក្តីសង្ខេបប្រចាំថ្ងៃ",
        "test": "សារសាកល្បង",
        "invoice_id": "លេខវិក្កយបត្រ",
        "document": "ឯកសារ",
        "customer": "អតិថិជន",
        "supplier": "អ្នកផ្គត់ផ្គង់",
        "phone": "ទូរស័ព្ទ",
        "payment_method": "ការបង់ប្រាក់",
        "delivery": "ដឹកជញ្ជូន",
        "products": "ទំនិញ",
        "subtotal": "សរុបរង",
        "delivery_fee": "តម្លៃដឹកជញ្ជូន",
        "discount": "បញ្ចុះតម្លៃ",
        "tax": "ពន្ធ",
        "total": "សរុប",
        "paid": "បានបង់",
        "debt": "បំណុល",
        "remaining": "បំណុលនៅសល់",
        "date": "កាលបរិច្ឆេទ",
        "by": "ដោយ",
        "walkin": "អតិថិជនទូទៅ",
        "sales": "ការលក់",
        "purchases": "ការទិញ",
        "customer_debt": "បំណុលអតិថិជននៅសល់",
        "supplier_debt": "បំណុលអ្នកផ្គត់ផ្គង់នៅសល់",
        "delivered": "បានដឹកជញ្ជូន",
        "pending_deliveries": "ការដឹកជញ្ជូនកំពុងរង់ចាំ",
        "out_of_stock": "ទំនិញអស់ស្តុក",
        "backup": "ការបម្រុងទុក Google Sheets",
        "backup_ok": "ការបម្រុងទុកបានសម្រេច",
        "backup_partial": "ការបម្រុងទុកបានសម្រេចដោយមានបញ្ហា",
        "backup_failed": "ការបម្រុងទុកបានបរាជ័យ",
        "backup_tables": "តារាង",
        "backup_new": "ជួរថ្មី",
        "backup_updated": "ជួរដែលបានកែ",
        "backup_skipped": "បានរំលង",
        "backup_failed_tables": "តារាងដែលបរាជ័យ",
        "backup_sheet": "Google Sheet",
    },
}

_METHOD_LABELS: dict[str, dict[str, str]] = {
    "en": {"CASH": "Cash", "BANK_QR": "Bank/QR", "CUSTOMER_DEBT": "Credit"},
    "km": {"CASH": "សាច់ប្រាក់", "BANK_QR": "ធនាគារ/QR", "CUSTOMER_DEBT": "ជំពាក់"},
}


def normalize_language(value) -> str:
    """Map any stored setting value onto a supported message language."""
    return "km" if str(value or "").strip().lower() == "km" else "en"


def _esc(value) -> str:
    """Escape dynamic text for Telegram HTML parse mode."""
    return html.escape(str(value if value is not None else ""), quote=False)


def _method_label(method, lang: str) -> str:
    raw = str(method or "").upper()
    return _METHOD_LABELS[lang].get(raw, raw or "-")


def _money(amount, currency) -> str:
    text = str(amount if amount is not None else "").strip()
    if not text:
        return "-"
    try:
        value = f"{Decimal(text):.2f}"
    except (ValueError, ArithmeticError):
        value = text
    return f"${value}" if str(currency or "USD").upper() == "USD" else f"៛{value}"


def _nonzero(value) -> bool:
    try:
        return Decimal(str(value or "0")) != 0
    except (ValueError, ArithmeticError):
        return False


def _fmt_qty(value) -> str:
    """Trim trailing zeros on a decimal quantity (2.0000 → 2)."""
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (ValueError, ArithmeticError):
        return str(value if value is not None else "-")


def _product_lines(items, currency, label: dict) -> list[str]:
    """Numbered product rows shared by the sale and purchase cards."""
    if not items:
        return []
    lines = ["", f"<b>{label['products']}:</b>"]
    for index, item in enumerate(items, start=1):
        name = _esc(item.get("name") or "-")
        quantity = _fmt_qty(item.get("quantity"))
        unit = str(item.get("uom") or "").strip()
        quantity_text = f"{quantity} {unit}".strip()
        price = _money(item.get("unit_price", item.get("unit_cost")), currency)
        line_total = _money(item.get("line_total"), currency)
        lines.append(f"{index}. {name} {quantity_text} @ {price} = {line_total}")
    return lines


async def telegram_enabled(session: AsyncSession) -> bool:
    """Master switch: settings.telegram.enabled and a saved/env bot token."""
    from app.core.config import settings as app_settings
    from app.shared.telegram.client import resolve_bot_token

    if not app_settings.telegram_enabled or not await resolve_bot_token(session):
        return False
    return bool(await get_setting_value(session, "telegram", "enabled", True))


async def recipients(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(User.telegram_chat_id).where(
            User.status == "ACTIVE",
            User.telegram_verified.is_(True),
            User.telegram_chat_id.is_not(None),
            User.telegram_chat_id != "",
        )
    )
    recipient_list = [str(chat_id) for chat_id in result.scalars().all()]
    # The Settings Telegram "Chat/Group ID" is a global fallback recipient
    # (e.g. a group chat) in addition to the verified per-user chats.
    configured = str(await get_setting_value(session, "telegram", "chat_id", "") or "").strip()
    if configured and configured not in recipient_list:
        recipient_list.append(configured)
    return recipient_list


async def _broadcast(session: AsyncSession, text: str, *, sender=None) -> int:
    """Send one text to every recipient. Returns the delivered count."""
    sender = sender or _default_sender
    delivered = 0
    for chat_id in await recipients(session):
        try:
            if await sender(chat_id, text):
                delivered += 1
        except Exception:  # noqa: BLE001 — one bad recipient must not stop the broadcast
            logger.exception("Telegram send failed for chat %s", chat_id)
    return delivered


async def _default_sender(chat_id: str, text: str) -> bool:
    from app.shared.telegram.client import send_message

    # Notification cards use Telegram HTML (bold titles, monospace codes).
    return await send_message(chat_id, text, parse_mode="HTML")


async def notification_language(session: AsyncSession) -> str:
    """Active message language from Settings (`telegram.notification_language`)."""
    value = await get_setting_value(session, "telegram", "notification_language", "en")
    return normalize_language(value)


def _local_today(session_tz: str) -> date:
    try:
        tz = ZoneInfo(session_tz or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


async def notify_sale(
    session: AsyncSession,
    *,
    invoice_no: str,
    occurred_at: datetime,
    customer: str | None,
    currency: str,
    exchange_rate,
    subtotal,
    discount,
    delivery_price,
    total,
    paid,
    payment_method: str,
    debt,
    cashier: str | None,
    item_count: int,
    customer_phone: str | None = None,
    items: list[dict] | None = None,
    sender=None,
) -> bool:
    """Sale notification (after commit). Never raises."""
    try:
        if not await get_setting_value(session, "telegram", "enabled", True):
            return False
        if not await get_setting_value(session, "telegram", "sale_enabled", False):
            return False
        tz_name = await get_setting_value(session, "system", "timezone", "UTC")
        text = format_sale_text(
            {
                "invoice_no": invoice_no,
                "occurred_at": occurred_at.isoformat(),
                "customer": customer,
                "customer_phone": customer_phone,
                "currency": currency,
                "exchange_rate": str(exchange_rate),
                "subtotal": str(subtotal),
                "discount": str(discount),
                "delivery_price": str(delivery_price),
                "total": str(total),
                "paid": str(paid),
                "payment_method": payment_method,
                "debt": str(debt),
                "cashier": cashier,
                "item_count": item_count,
                "items": items or [],
            },
            timezone_name=str(tz_name or "UTC"),
            lang=await notification_language(session),
        )
        sent = await _broadcast(session, text, sender=sender)
        return sent > 0
    except Exception:
        logger.exception("Telegram sale notification failed for %s", invoice_no)
        return False


async def notify_purchase(
    session: AsyncSession,
    *,
    document_no: str,
    occurred_at: datetime,
    supplier: str | None,
    currency: str,
    exchange_rate,
    subtotal,
    discount,
    tax,
    total,
    paid,
    debt,
    user: str | None,
    item_count: int,
    items: list[dict] | None = None,
    sender=None,
) -> bool:
    """Stock In (purchase) notification (after commit). Never raises."""
    try:
        if not await get_setting_value(session, "telegram", "enabled", True):
            return False
        if not await get_setting_value(session, "telegram", "purchase_enabled", False):
            return False
        tz_name = await get_setting_value(session, "system", "timezone", "UTC")
        text = format_purchase_text(
            {
                "document_no": document_no,
                "occurred_at": occurred_at.isoformat(),
                "supplier": supplier,
                "currency": currency,
                "exchange_rate": str(exchange_rate),
                "subtotal": str(subtotal),
                "discount": str(discount),
                "tax": str(tax),
                "total": str(total),
                "paid": str(paid),
                "debt": str(debt),
                "user": user,
                "item_count": item_count,
                "items": items or [],
            },
            timezone_name=str(tz_name or "UTC"),
            lang=await notification_language(session),
        )
        sent = await _broadcast(session, text, sender=sender)
        return sent > 0
    except Exception:
        logger.exception("Telegram purchase notification failed for %s", document_no)
        return False


async def notify_payment_text(
    session: AsyncSession,
    *,
    invoice_no: str,
    payment_no: str,
    customer: str | None,
    total,
    paid,
    payment_method: str,
    remaining,
    cashier: str | None,
    currency: str = "USD",
    sender=None,
) -> bool:
    """Debt-payment text notification (after commit). Never raises.

    Gated by the sale-notification toggle: debt payments are the payment
    stream of the sale, not invoice documents (no files are ever sent)."""
    try:
        if not await get_setting_value(session, "telegram", "enabled", True):
            return False
        if not await get_setting_value(session, "telegram", "sale_enabled", False):
            return False
        tz_name = await get_setting_value(session, "system", "timezone", "UTC")
        text = format_payment_text(
            {
                "invoice_no": invoice_no,
                "payment_no": payment_no,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "customer": customer,
                "currency": currency,
                "total": str(total),
                "paid": str(paid),
                "payment_method": payment_method,
                "remaining": str(remaining),
                "cashier": cashier,
            },
            timezone_name=str(tz_name or "UTC"),
            lang=await notification_language(session),
        )
        sent = await _broadcast(session, text, sender=sender)
        return sent > 0
    except Exception:
        logger.exception("Telegram payment notification failed for %s", invoice_no)
        return False


async def notify_supplier_payment_text(
    session: AsyncSession,
    *,
    document_no: str | None,
    payment_no: str,
    supplier: str | None,
    total,
    paid,
    payment_method: str,
    remaining,
    cashier: str | None,
    currency: str = "USD",
    sender=None,
) -> bool:
    """Supplier debt-payment text notification (after commit). Never raises.

    Supplier debts originate from Stock In, so the purchase toggle gates it."""
    try:
        if not await get_setting_value(session, "telegram", "enabled", True):
            return False
        if not await get_setting_value(session, "telegram", "purchase_enabled", False):
            return False
        tz_name = await get_setting_value(session, "system", "timezone", "UTC")
        text = format_supplier_payment_text(
            {
                "document_no": document_no,
                "payment_no": payment_no,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "supplier": supplier,
                "currency": currency,
                "total": str(total),
                "paid": str(paid),
                "payment_method": payment_method,
                "remaining": str(remaining),
                "cashier": cashier,
            },
            timezone_name=str(tz_name or "UTC"),
            lang=await notification_language(session),
        )
        sent = await _broadcast(session, text, sender=sender)
        return sent > 0
    except Exception:
        logger.exception("Telegram supplier payment notification failed for %s", payment_no)
        return False


async def send_test_notification(session: AsyncSession, *, sender=None) -> dict:
    """Settings-driven connectivity test (Administration → Settings)."""
    if not await telegram_enabled(session):
        return {"enabled": False, "sent": 0, "recipients": 0}
    tz_name = await get_setting_value(session, "system", "timezone", "UTC")
    lang = await notification_language(session)
    label = _LABELS[lang]
    text = (
        f"{_EMOJI['test']} <b>{label['test']}</b>\n\n"
        f"Stock & POS\n"
        f"{label['date']}: {_esc(datetime.now(timezone.utc).isoformat(timespec='seconds'))}\n"
        f"Timezone: {_esc(tz_name)}"
    )
    chats = await recipients(session)
    sent = await _broadcast(session, text, sender=sender)
    return {"enabled": True, "sent": sent, "recipients": len(chats)}


# ------------------------------------------------------------------ formatters


def _stamp(raw: str, timezone_name: str) -> str:
    try:
        moment = datetime.fromisoformat(str(raw))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo("UTC"))
        try:
            moment = moment.astimezone(ZoneInfo(timezone_name or "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            moment = moment.astimezone(ZoneInfo("UTC"))
        return moment.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    except ValueError:
        return str(raw)


def format_sale_text(payload: dict, *, timezone_name: str = "UTC", lang: str = "en") -> str:
    """Receipt-style HTML sale card. Never includes invoice files/PDFs."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    currency = payload.get("currency") or "USD"
    lines = [f"{_EMOJI['sale']} <b>{label['sale']}</b>", ""]
    lines.append(f"{label['invoice_id']}: {_esc(payload.get('invoice_no', '-'))}")
    lines.append(f"{label['customer']}: {_esc(payload.get('customer') or label['walkin'])}")
    if payload.get("customer_phone"):
        lines.append(f"{label['phone']}: {_esc(payload['customer_phone'])}")
    lines.append(
        f"{label['payment_method']}: {_esc(_method_label(payload.get('payment_method'), lang))}"
    )
    if _nonzero(payload.get("delivery_price")):
        lines.append(f"{label['delivery']}: {_money(payload['delivery_price'], currency)}")

    lines.extend(_product_lines(payload.get("items"), currency, label))

    lines.append("")
    if payload.get("subtotal") is not None:
        lines.append(f"{label['subtotal']}: {_money(payload['subtotal'], currency)}")
    if _nonzero(payload.get("delivery_price")):
        lines.append(f"{label['delivery_fee']}: {_money(payload['delivery_price'], currency)}")
    if _nonzero(payload.get("discount")):
        lines.append(f"{label['discount']}: {_money(payload['discount'], currency)}")
    lines.append(f"<b>{label['total']}: {_money(payload.get('total'), currency)}</b>")
    if payload.get("paid") is not None:
        lines.append(f"{label['paid']}: {_money(payload['paid'], currency)}")
    if _nonzero(payload.get("debt")):
        lines.append(f"{label['debt']}: {_money(payload['debt'], currency)}")
    lines.append("")
    lines.append(f"{label['date']}: {_esc(_stamp(payload.get('occurred_at', ''), timezone_name))}")
    if payload.get("cashier"):
        lines.append(f"{label['by']}: {_esc(payload['cashier'])}")
    return "\n".join(lines)


def format_purchase_text(payload: dict, *, timezone_name: str = "UTC", lang: str = "en") -> str:
    """Receipt-style HTML purchase (Stock In) card."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    currency = payload.get("currency") or "USD"
    lines = [f"{_EMOJI['purchase']} <b>{label['purchase']}</b>", ""]
    lines.append(f"{label['document']}: {_esc(payload.get('document_no', '-'))}")
    if payload.get("supplier"):
        lines.append(f"{label['supplier']}: {_esc(payload['supplier'])}")

    lines.extend(_product_lines(payload.get("items"), currency, label))

    lines.append("")
    if payload.get("subtotal") is not None:
        lines.append(f"{label['subtotal']}: {_money(payload['subtotal'], currency)}")
    if _nonzero(payload.get("discount")):
        lines.append(f"{label['discount']}: {_money(payload['discount'], currency)}")
    if _nonzero(payload.get("tax")):
        lines.append(f"{label['tax']}: {_money(payload['tax'], currency)}")
    lines.append(f"<b>{label['total']}: {_money(payload.get('total'), currency)}</b>")
    if payload.get("paid") is not None:
        lines.append(f"{label['paid']}: {_money(payload['paid'], currency)}")
    if _nonzero(payload.get("debt")):
        lines.append(f"{label['debt']}: {_money(payload['debt'], currency)}")
    lines.append("")
    lines.append(f"{label['date']}: {_esc(_stamp(payload.get('occurred_at', ''), timezone_name))}")
    if payload.get("user"):
        lines.append(f"{label['by']}: {_esc(payload['user'])}")
    return "\n".join(lines)


def format_payment_text(payload: dict, *, timezone_name: str = "UTC", lang: str = "en") -> str:
    """Receipt-style HTML customer debt-payment card (text only)."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    currency = payload.get("currency") or "USD"
    lines = [f"{_EMOJI['payment']} <b>{label['payment']}</b>", ""]
    lines.append(f"{label['invoice_id']}: {_esc(payload.get('invoice_no', '-'))}")
    if payload.get("payment_no"):
        lines.append(f"{label['document']}: {_esc(payload['payment_no'])}")
    lines.append(f"{label['customer']}: {_esc(payload.get('customer') or label['walkin'])}")
    lines.append(
        f"{label['payment_method']}: {_esc(_method_label(payload.get('payment_method'), lang))}"
    )
    lines.append("")
    lines.append(f"<b>{label['paid']}: {_money(payload.get('paid'), currency)}</b>")
    if payload.get("total") is not None:
        lines.append(f"{label['total']}: {_money(payload['total'], currency)}")
    if payload.get("remaining") is not None:
        lines.append(f"{label['remaining']}: {_money(payload['remaining'], currency)}")
    lines.append("")
    lines.append(f"{label['date']}: {_esc(_stamp(payload.get('occurred_at', ''), timezone_name))}")
    if payload.get("cashier"):
        lines.append(f"{label['by']}: {_esc(payload['cashier'])}")
    return "\n".join(lines)


def format_supplier_payment_text(payload: dict, *, timezone_name: str = "UTC", lang: str = "en") -> str:
    """Receipt-style HTML supplier debt-payment card."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    currency = payload.get("currency") or "USD"
    lines = [f"{_EMOJI['supplier_payment']} <b>{label['supplier_payment']}</b>", ""]
    lines.append(f"{label['document']}: {_esc(payload.get('document_no') or '-')}")
    if payload.get("payment_no"):
        lines.append(f"{label['invoice_id']}: {_esc(payload['payment_no'])}")
    if payload.get("supplier"):
        lines.append(f"{label['supplier']}: {_esc(payload['supplier'])}")
    lines.append(
        f"{label['payment_method']}: {_esc(_method_label(payload.get('payment_method'), lang))}"
    )
    lines.append("")
    lines.append(f"<b>{label['paid']}: {_money(payload.get('paid'), currency)}</b>")
    if payload.get("total") is not None:
        lines.append(f"{label['total']}: {_money(payload['total'], currency)}")
    if payload.get("remaining") is not None:
        lines.append(f"{label['remaining']}: {_money(payload['remaining'], currency)}")
    lines.append("")
    lines.append(f"{label['date']}: {_esc(_stamp(payload.get('occurred_at', ''), timezone_name))}")
    if payload.get("cashier"):
        lines.append(f"{label['by']}: {_esc(payload['cashier'])}")
    return "\n".join(lines)


# ------------------------------------------------------------- daily summary


async def daily_summary_totals(session: AsyncSession, *, day: date | None = None) -> dict:
    """Aggregated operational numbers for one local day.

    USD and KHR totals are NEVER summed together — every amount stays in its
    document currency and the summary reports both columns separately.
    """
    from app.modules.customers.models import CustomerDebt
    from app.modules.delivery.models import DeliveryNote
    from app.modules.pos.models import Sale
    from app.modules.stock.models import Product, StockBalance, StockTransaction, StockTransactionItem
    from app.modules.suppliers.models import SupplierDebt

    timezone_name = str(await get_setting_value(session, "system", "timezone", "UTC") or "UTC")
    day = day or _local_today(timezone_name)
    # Shop-local day boundaries → UTC [start, end). Using the timezone (rather
    # than a UTC calendar date) keeps "today" correct for the operator.
    from app.shared.telegram.summary import shop_timezone, utc_window

    day_start, day_end = utc_window(day, day, shop_timezone(timezone_name))

    async def currency_totals(stmt_model, date_col, total_expr=None):
        rows = await session.execute(
            select(
                stmt_model.currency,
                func.count(),
                func.coalesce(func.sum(total_expr if total_expr is not None else stmt_model.grand_total), 0),
            )
            .where(date_col >= day_start, date_col < day_end)
            .group_by(stmt_model.currency)
        )
        out: dict[str, dict[str, object]] = {}
        for currency, count, total in rows.all():
            out[str(currency)] = {"count": int(count), "total": Decimal(total).quantize(Decimal("0.01"))}
        return out

    sales = await currency_totals(Sale, Sale.sale_date)
    # Purchase total per document = sum(item.line_total) − discount + tax.
    items_subtotal = (
        select(
            StockTransactionItem.stock_transaction_id.label("tx_id"),
            func.coalesce(func.sum(StockTransactionItem.line_total), 0).label("subtotal"),
        )
        .group_by(StockTransactionItem.stock_transaction_id)
        .subquery()
    )
    purchase_rows = await session.execute(
        select(
            StockTransaction.currency,
            func.count(),
            func.coalesce(
                func.sum(items_subtotal.c.subtotal - StockTransaction.discount_amount + StockTransaction.tax_amount),
                0,
            ),
        )
        .join(items_subtotal, items_subtotal.c.tx_id == StockTransaction.id)
        .where(
            StockTransaction.transaction_date >= day_start,
            StockTransaction.transaction_date < day_end,
            StockTransaction.transaction_type == "STOCK_IN",
        )
        .group_by(StockTransaction.currency)
    )
    purchases = {
        str(currency): {"count": int(count), "total": Decimal(total).quantize(Decimal("0.01"))}
        for currency, count, total in purchase_rows.all()
    }

    customer_debt_total = Decimal(
        (
            await session.execute(
                select(func.coalesce(func.sum(CustomerDebt.remaining_amount), 0)).where(
                    CustomerDebt.status != "PAID"
                )
            )
        ).scalar_one()
    )
    supplier_debt_total = Decimal(
        (
            await session.execute(
                select(func.coalesce(func.sum(SupplierDebt.remaining_amount), 0)).where(
                    SupplierDebt.status != "PAID"
                )
            )
        ).scalar_one()
    )

    # Delivery notes CREATED in the selected local day (classified by their
    # current status) — not an all-time snapshot.
    deliveries = (
        await session.execute(
            select(DeliveryNote.status, func.count())
            .where(DeliveryNote.created_at >= day_start, DeliveryNote.created_at < day_end)
            .group_by(DeliveryNote.status)
        )
    ).all()
    delivery_counts = {str(status): int(count) for status, count in deliveries}
    delivered_count = delivery_counts.get("DELIVERED", 0)
    pending_delivery_count = sum(
        count
        for status, count in delivery_counts.items()
        if status not in ("DELIVERED", "RETURNED", "FAILED")
    )

    out_of_stock = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Product)
                .join(StockBalance, StockBalance.product_id == Product.id)
                .where(
                    Product.status == "ACTIVE",
                    StockBalance.quantity <= 0,
                )
            )
        ).scalar_one()
    )

    return {
        "day": day.isoformat(),
        "sales": {currency: {"count": row["count"], "total": str(row["total"])} for currency, row in sales.items()},
        "purchases": {currency: {"count": row["count"], "total": str(row["total"])} for currency, row in purchases.items()},
        "customer_debt_total": str(customer_debt_total.quantize(Decimal("0.01"))),
        "supplier_debt_total": str(supplier_debt_total.quantize(Decimal("0.01"))),
        "delivered_count": delivered_count,
        "pending_delivery_count": pending_delivery_count,
        "out_of_stock_count": out_of_stock,
    }


def format_daily_summary_text(summary: dict, *, lang: str = "en") -> str:
    """Render the daily summary; USD and KHR columns are kept separate."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    lines = [f"{_EMOJI['daily']} <b>{label['daily']} {summary.get('day', '')}</b>", ""]

    sales = summary.get("sales") or {}
    sale_count = sum(int(row["count"]) for row in sales.values())
    lines.append(f"{label['sales']}: {sale_count}")
    for currency in ("USD", "KHR"):
        if sales.get(currency):
            lines.append(f"  {currency} {label['sales']}: {sales[currency]['total']}")

    purchases = summary.get("purchases") or {}
    purchase_count = sum(int(row["count"]) for row in purchases.values())
    lines.append(f"{label['purchases']}: {purchase_count}")
    for currency in ("USD", "KHR"):
        if purchases.get(currency):
            lines.append(f"  {currency} {label['purchases']}: {purchases[currency]['total']}")

    lines.append(f"{label['customer_debt']}: {summary.get('customer_debt_total', '-')}")
    lines.append(f"{label['supplier_debt']}: {summary.get('supplier_debt_total', '-')}")
    lines.append(f"{label['delivered']}: {summary.get('delivered_count', 0)}")
    lines.append(f"{label['pending_deliveries']}: {summary.get('pending_delivery_count', 0)}")
    lines.append(f"{label['out_of_stock']}: {summary.get('out_of_stock_count', 0)}")
    return "\n".join(lines)


async def send_daily_summary(session: AsyncSession, *, sender=None, day: date | None = None) -> dict:
    """Build and broadcast the daily summary. Never raises into the scheduler."""
    try:
        if not await get_setting_value(session, "telegram", "daily_summary_enabled", False):
            return {"enabled": False, "sent": 0}
        if not await telegram_enabled(session):
            return {"enabled": False, "sent": 0}
        summary = await daily_summary_totals(session, day=day)
        text = format_daily_summary_text(summary, lang=await notification_language(session))
        sent = await _broadcast(session, text, sender=sender)
        return {"enabled": True, "sent": sent, "summary": summary}
    except Exception:
        logger.exception("Telegram daily summary failed")
        return {"enabled": False, "sent": 0, "error": True}


# --------------------------------------------------------------------- backup


def format_backup_text(job, *, lang: str = "en", spreadsheet: str = "") -> str:
    """Compact Google Sheets backup result card (success / partial / failed)."""
    lang = normalize_language(lang)
    label = _LABELS[lang]
    status = str(getattr(job, "status", "") or "")
    title_key = {
        "success": "backup_ok",
        "partial": "backup_partial",
        "failed": "backup_failed",
    }.get(status, "backup_failed")
    lines = [f"{_EMOJI['backup']} <b>{label['backup']}</b>", "", f"<b>{label[title_key]}</b>"]
    if spreadsheet:
        lines.append(f"{label['backup_sheet']}: {_esc(spreadsheet)}")
    lines.append(
        f"{label['backup_tables']}: {int(getattr(job, 'tables_succeeded', 0) or 0)}/"
        f"{int(getattr(job, 'tables_total', 0) or 0)}"
    )
    lines.append(f"{label['backup_new']}: {int(getattr(job, 'rows_appended', 0) or 0)}")
    lines.append(f"{label['backup_updated']}: {int(getattr(job, 'rows_updated', 0) or 0)}")
    lines.append(f"{label['backup_skipped']}: {int(getattr(job, 'rows_skipped', 0) or 0)}")
    failed = int(getattr(job, "tables_failed", 0) or 0)
    if failed:
        lines.append(f"{label['backup_failed_tables']}: {failed}")
    if getattr(job, "error_message", None):
        lines.append(_esc(str(job.error_message)[:300]))
    finished = getattr(job, "finished_at", None)
    if finished is not None:
        lines.append("")
        lines.append(f"{label['date']}: {_esc(finished.isoformat(timespec='seconds'))}")
    return "\n".join(lines)


async def notify_backup_result(session: AsyncSession, *, job, spreadsheet: str = "", sender=None) -> int:
    """Broadcast a backup result. Never raises into the backup run."""
    try:
        if not await telegram_enabled(session):
            return 0
        text = format_backup_text(
            job, lang=await notification_language(session), spreadsheet=spreadsheet
        )
        return await _broadcast(session, text, sender=sender)
    except Exception:
        logger.exception("Telegram backup notification failed")
        return 0
