"""Payment / invoice Telegram text is forbidden. Invoices print in the browser only.

`queue_payment_invoice_notify` is a no-op so existing POS/debt hooks never
block a committed transaction. The formatter remains for unit tests only.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("stock_pos.telegram")


def format_payment_invoice_text(payload: dict, *, shop_name: str, timezone_name: str = "UTC") -> str:
    """Render a plain-text invoice summary. Do not send this over Telegram."""
    stamp = str(payload.get("occurred_at") or "")
    raw = payload.get("occurred_at")
    if raw:
        try:
            moment = datetime.fromisoformat(str(raw))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=ZoneInfo("UTC"))
            try:
                moment = moment.astimezone(ZoneInfo(timezone_name or "UTC"))
            except (ZoneInfoNotFoundError, ValueError):
                moment = moment.astimezone(ZoneInfo("UTC"))
            stamp = moment.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        except ValueError:
            pass

    def money(key: str) -> str | None:
        value = payload.get(key)
        return None if value is None else str(value)

    lines = [str(shop_name or "Yoeun Sokhon Pharmacy")]
    lines.append(f"Invoice: {payload.get('invoice_no', '-')}")
    if payload.get("payment_no"):
        lines.append(f"Payment: {payload['payment_no']}")
    lines.append(f"Date: {stamp}")
    lines.append(f"Customer: {payload.get('customer') or 'Walk-in Customer'}")
    if payload.get("item_count") is not None:
        lines.append(f"Items: {payload['item_count']}")
    if money("subtotal") is not None:
        lines.append(f"Subtotal: {money('subtotal')}")
    if money("discount") is not None:
        lines.append(f"Discount: {money('discount')}")
    if money("total") is not None:
        lines.append(f"Total: {money('total')}")
    if money("paid") is not None:
        lines.append(f"Paid: {money('paid')}")
    if payload.get("payment_method"):
        lines.append(f"Method: {payload['payment_method']}")
    if money("remaining") is not None:
        lines.append(f"Remaining debt: {money('remaining')}")
    if payload.get("cashier"):
        lines.append(f"Cashier: {payload['cashier']}")
    return "\n".join(lines)


def queue_payment_invoice_notify(payload: dict) -> bool:
    """No-op. Spec forbids Telegram payment/invoice send."""
    logger.debug("Telegram payment/invoice notify is disabled")
    return False
