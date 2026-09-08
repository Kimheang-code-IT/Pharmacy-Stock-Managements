"""Telegram bot process (Compose service `telegram-bot`).

Inbound (long polling), view-only (spec sections 3.6 / 3.6.1):
- /start replies with the chat's Telegram Chat ID so administrators can copy
  it into Administration > Users.
- linked users get the view-only inquiry keyboard: Current Stock, Low Stock,
  Expiring Soon, Sales Summary (period select), Help. Every tool calls the
  read-only adapters in `app.shared.telegram.inquiry`; the bot never writes
  to the database. Any unknown/write-shaped callback is refused ("View only").

Outbound password-reset delivery is queued through RabbitMQ and sent by the
`worker-telegram` Celery worker (`app.tasks.telegram`) — unchanged.

Secrets (bot token, client secret) come from environment only.
"""

import asyncio
import logging

from app.core.config import settings
from app.shared.telegram.inquiry import (
    VIEW_ONLY_REPLY,
    InquiryAction,
    route_callback,
    resolve_access,
    run_tool,
)

logger = logging.getLogger("stock_pos.telegram_bot")

TOOL_LABELS = {
    "current_stock": "Current Stock",
    "low_stock": "Low Stock",
    "expiring": "Expiring Soon",
    "sales": "Sales Summary",
}
PERIOD_LABELS = {"today": "Today", "7d": "Last 7 days", "month": "This month"}


async def _idle_forever() -> None:
    logger.warning("TELEGRAM_BOT_TOKEN is not configured; telegram bot is idle")
    while True:
        await asyncio.sleep(60)


def _menu_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(TOOL_LABELS["current_stock"], callback_data="tool:current_stock"),
                InlineKeyboardButton(TOOL_LABELS["low_stock"], callback_data="tool:low_stock"),
            ],
            [
                InlineKeyboardButton(TOOL_LABELS["expiring"], callback_data="tool:expiring"),
                InlineKeyboardButton(TOOL_LABELS["sales"], callback_data="tool:sales"),
            ],
            [InlineKeyboardButton("Help", callback_data="help")],
        ]
    )


def _period_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(PERIOD_LABELS[period], callback_data=f"page:sales:{period}:1")
                for period in PERIOD_LABELS
            ],
            [InlineKeyboardButton("Menu", callback_data="menu")],
        ]
    )


def _result_keyboard(action: InquiryAction, total_pages: int):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    page = min(max(1, action.page), total_pages)
    rows = []
    if total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    "Prev", callback_data=f"page:{action.tool}:{action.period or '-'}:{max(1, page - 1)}"
                ),
                InlineKeyboardButton("Menu", callback_data="menu"),
                InlineKeyboardButton(
                    "Next", callback_data=f"page:{action.tool}:{action.period or '-'}:{min(total_pages, page + 1)}"
                ),
            ]
        )
    else:
        rows.append([InlineKeyboardButton("Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


async def _reply_instruction(update, text: str) -> None:
    """Send an instruction that never contains business data."""
    message = update.effective_message
    if message:
        await message.reply_text(text)


async def on_start(update, context) -> None:
    """Menu for linked users; Chat ID link instruction otherwise."""
    chat = update.effective_chat
    if not chat:
        return
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        _, error = await resolve_access(session, str(chat.id))
    if error:
        await _reply_instruction(update, error)
        return
    if update.message:
        await update.message.reply_text("Stock & POS inquiry — choose a tool:", reply_markup=_menu_keyboard())


async def on_help(update, context) -> None:
    from app.shared.telegram.inquiry import HELP_TEXT

    if update.message:
        await update.message.reply_text(HELP_TEXT)


async def on_link(update, context) -> None:
    """`/link CODE` — bind this chat to the account that issued the code."""
    chat = update.effective_chat
    if not chat or not update.message:
        return
    code = " ".join(context.args or []).strip()
    if not code:
        await update.message.reply_text(
            "Usage: /link CODE — generate the code in the app "
            "(Profile > Link Telegram)."
        )
        return
    from app.core.database import SessionFactory
    from app.shared.telegram.linking import consume_link_code

    async with SessionFactory() as session:
        user = await consume_link_code(session, code, str(chat.id))
    if user is None:
        await update.message.reply_text(
            "Invalid or expired link code. Generate a new one in the app and try again."
        )
        return
    await update.message.reply_text(
        "Telegram linked. You can now use the view-only stock inquiry menu."
    )


async def on_text(update, context) -> None:
    """Non-command text: linked users get the menu; unlinked get the link hint."""
    chat = update.effective_chat
    if not chat or not update.message:
        return
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        _, error = await resolve_access(session, str(chat.id))
    if error:
        await _reply_instruction(update, error)
        return
    await update.message.reply_text("Choose a tool:", reply_markup=_menu_keyboard())


async def on_callback(update, context) -> None:
    """View-only callback dispatcher (spec section 3.6.1)."""
    query = update.callback_query
    if query is None:
        return
    action = route_callback(query.data)
    if action is None:
        # Write attempt or unknown payload: refuse and ignore. No business data.
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        logger.warning("Refused non-read-only callback from chat %s: %r", chat_id, query.data)
        await query.answer(VIEW_ONLY_REPLY, show_alert=True)
        if query.message:
            await query.message.reply_text(VIEW_ONLY_REPLY)
        return

    chat = update.effective_chat
    if not chat:
        return
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        _, error = await resolve_access(session, str(chat.id))
        if error:
            await query.answer()
            await _reply_instruction(update, error)
            return
        if action.tool == "help":
            from app.shared.telegram.inquiry import HELP_TEXT

            await query.answer()
            if query.message:
                await query.message.reply_text(HELP_TEXT)
            return
        if action.tool == "menu":
            await query.answer()
            if query.message:
                await query.message.reply_text("Choose a tool:", reply_markup=_menu_keyboard())
            return
        if action.tool == "sales" and not action.period:
            await query.answer()
            if query.message:
                await query.message.reply_text("Choose a period:", reply_markup=_period_keyboard())
            return
        text, total_pages = await run_tool(session, action)
    await query.answer()
    if query.message:
        await query.message.reply_text(text, reply_markup=_result_keyboard(action, total_pages))


def run() -> None:
    token = settings.telegram_bot_token
    if not token:
        asyncio.run(_idle_forever())
        return

    from telegram import Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("help", on_help))
    application.add_handler(CommandHandler("menu", on_start))
    application.add_handler(CommandHandler("link", on_link))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    logger.info("Telegram bot started (mode=%s)", settings.telegram_bot_mode)
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    run()
