"""Telegram bot process (Compose service `telegram-bot`).

Inbound (long polling), view-only (spec sections 3.6 / 3.6.1):

- /start replies with the chat's Telegram Chat ID for administrators to copy
  into Administration > Users; linked users get the reply-keyboard menu.
- The whole inquiry flow uses **reply keyboards only** (buttons below the
  conversation): a main menu (Summary / Current Stock / Low Stock / Expiring
  Soon / Help), a Summary period picker (Today / Last 7 Days / This Month /
  Custom Date Range / Back to Menu) and Previous / Next pagination for stock
  lists. No inline keyboards are attached to bot messages.
- Every tool calls the read-only adapters in `app.shared.telegram.inquiry`
  and `app.shared.telegram.summary`; the bot never writes to the database.

Outbound password-reset delivery is sent in-process by the API
(`app.shared.telegram.delivery`) — no Celery/RabbitMQ worker.

The bot token and group ID are configured entirely from Administration >
Settings (SPA); the bot watches the saved token and reloads within seconds when
an operator changes it, without a container restart.
"""

import asyncio
import logging

from app.shared.telegram import keyboards as kb
from app.shared.telegram.inquiry import (
    HELP_TEXT,
    NO_PERMISSION_REPLY,
    InquiryAction,
    check_tool_permission,
    resolve_access,
    run_tool,
)
from app.shared.telegram.summary import (
    PERIOD_7D,
    PERIOD_MONTH,
    PERIOD_TODAY,
    SummaryConversation,
    custom_range_error,
    max_custom_range_days,
    parse_iso_date,
    period_summary,
    render_summary,
    resolve_period,
    shop_timezone,
    utc_window,
)

logger = logging.getLogger("stock_pos.telegram_bot")

# Per-chat conversation state (custom date entry + stock pagination).
conversations = SummaryConversation()

_PERIOD_ACTIONS = {
    kb.ACTION_TODAY: PERIOD_TODAY,
    kb.ACTION_7D: PERIOD_7D,
    kb.ACTION_MONTH: PERIOD_MONTH,
}
_STOCK_TOOLS = (kb.ACTION_CURRENT_STOCK, kb.ACTION_LOW_STOCK, kb.ACTION_EXPIRING)

_DATE_PROMPT = "Send the date in YYYY-MM-DD format (e.g. 2026-09-30)."


# How long to wait before re-checking Settings when no token is saved yet, and
# how often to watch for a token change while polling (fast pickup, no restart).
_TOKEN_RETRY_SECONDS = 5
_TOKEN_WATCH_SECONDS = 5


async def _language(session) -> str:
    from app.shared.telegram.service import notification_language

    return await notification_language(session)


async def _timezone(session):
    from app.modules.administration.service import get_setting_value

    name = str(await get_setting_value(session, "system", "timezone", "UTC") or "UTC")
    return shop_timezone(name)


async def _send(update, text: str, spec: list[list[str]] | None = None) -> None:
    """Reply with text and (optionally) a reply keyboard. No inline buttons."""
    message = update.effective_message
    if message is None:
        return
    if spec is None:
        await message.reply_text(text)
    else:
        await message.reply_text(text, reply_markup=kb.to_reply_markup(spec))


async def _send_menu(update, lang: str) -> None:
    await _send(update, "Stock & POS inquiry — choose a tool:", kb.menu_keyboard_spec(lang))


async def _send_periods(update, lang: str) -> None:
    await _send(update, "Choose a period:", kb.period_keyboard_spec(lang))


async def on_start(update, context) -> None:
    """Menu for linked users; Chat ID link instruction otherwise."""
    chat = update.effective_chat
    if not chat:
        return
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        user, error = await resolve_access(session, str(chat.id))
        if error:
            await _send(update, error)
            return
        lang = await _language(session)
    conversations.reset(str(chat.id))
    await _send_menu(update, lang)


async def on_help(update, context) -> None:
    chat = update.effective_chat
    if not chat:
        return
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        _, error = await resolve_access(session, str(chat.id))
        if error:
            await _send(update, error)
            return
        lang = await _language(session)
    await _send(update, HELP_TEXT, kb.menu_keyboard_spec(lang))


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
        "Telegram linked. You can now use the view-only inquiry menu."
    )


async def on_text(update, context) -> None:
    """Reply-keyboard button or conversation text (e.g. a custom date)."""
    chat = update.effective_chat
    message = update.message
    if not chat or not message:
        return
    text = message.text or ""
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        user, error = await resolve_access(session, str(chat.id))
        if error:
            conversations.reset(str(chat.id))
            await _send(update, error)
            return
        lang = await _language(session)
        action = kb.route_text(text)
        if action is not None:
            await _dispatch(update, session, user, lang, action)
            return
        # Free text: only meaningful while collecting a custom date range.
        step = conversations.custom_step(str(chat.id))
        if step:
            await _handle_custom_date(update, session, user, lang, step, text)
            return
        await _send_menu(update, lang)


async def _dispatch(update, session, user, lang: str, action: str) -> None:
    chat_id = str(update.effective_chat.id)

    if action == kb.ACTION_MENU:
        conversations.reset(chat_id)
        await _send_menu(update, lang)
        return
    if action == kb.ACTION_HELP:
        await _send(update, HELP_TEXT, kb.menu_keyboard_spec(lang))
        return
    if action == kb.ACTION_SUMMARY:
        conversations.cancel_custom(chat_id)
        conversations.clear_pager(chat_id)
        await _send_periods(update, lang)
        return
    if action in _PERIOD_ACTIONS:
        conversations.cancel_custom(chat_id)
        await _run_period_summary(update, session, user, lang, _PERIOD_ACTIONS[action])
        return
    if action == kb.ACTION_CUSTOM:
        conversations.begin_custom(chat_id)
        await _send(update, f"Send the start date. {_DATE_PROMPT}", kb.custom_keyboard_spec(lang))
        return
    if action == kb.ACTION_CANCEL:
        conversations.reset(chat_id)
        await _send(update, "Cancelled.", kb.menu_keyboard_spec(lang))
        return
    if action in (kb.ACTION_PREV, kb.ACTION_NEXT):
        await _run_pager(update, session, user, lang, action)
        return
    if action in _STOCK_TOOLS:
        conversations.cancel_custom(chat_id)
        await _run_stock_tool(update, session, user, lang, tool=action, page=1)
        return


async def _run_period_summary(update, session, user, lang: str, period: str) -> None:
    tz = await _timezone(session)
    local_start, local_end = resolve_period(period, tz=tz)
    utc_start, utc_end = utc_window(local_start, local_end, tz)
    summary = await period_summary(
        session,
        utc_start=utc_start,
        utc_end=utc_end,
        local_start=local_start,
        local_end=local_end,
        user=user,
    )
    await _send(update, render_summary(summary, lang=lang), kb.period_keyboard_spec(lang))


async def _run_custom_summary(update, session, user, lang: str, start, end) -> None:
    tz = await _timezone(session)
    utc_start, utc_end = utc_window(start, end, tz)
    summary = await period_summary(
        session,
        utc_start=utc_start,
        utc_end=utc_end,
        local_start=start,
        local_end=end,
        user=user,
    )
    await _send(update, render_summary(summary, lang=lang), kb.period_keyboard_spec(lang))


async def _handle_custom_date(update, session, user, lang: str, step: str, text: str) -> None:
    chat_id = str(update.effective_chat.id)
    parsed = parse_iso_date(text)
    if parsed is None:
        await _send(
            update,
            f"That is not a valid date. {_DATE_PROMPT}",
            kb.custom_keyboard_spec(lang),
        )
        return
    if step == "start":
        conversations.set_custom_start(chat_id, parsed)
        await _send(update, f"Send the end date. {_DATE_PROMPT}", kb.custom_keyboard_spec(lang))
        return
    # step == "end"
    start = conversations.custom_start(chat_id)
    error = custom_range_error(start, parsed, max_days=await max_custom_range_days(session))
    if error:
        await _send(update, f"{error} {_DATE_PROMPT}", kb.custom_keyboard_spec(lang))
        return
    conversations.cancel_custom(chat_id)
    await _run_custom_summary(update, session, user, lang, start, parsed)


async def _run_stock_tool(update, session, user, lang: str, *, tool: str, page: int) -> None:
    chat_id = str(update.effective_chat.id)
    # Role check mirrors the HTTP stock API: a verified chat alone is not enough.
    if not check_tool_permission(user, tool):
        await _send(update, NO_PERMISSION_REPLY, kb.menu_keyboard_spec(lang))
        return
    text, total_pages = await run_tool(session, InquiryAction(tool=tool, page=page), user=user)
    conversations.set_pager(chat_id, tool, min(max(1, page), total_pages))
    await _send(update, text, kb.pagination_keyboard_spec(lang))


async def _run_pager(update, session, user, lang: str, action: str) -> None:
    chat_id = str(update.effective_chat.id)
    pager = conversations.pager(chat_id)
    if not pager:
        await _send_menu(update, lang)
        return
    step = 1 if action == kb.ACTION_NEXT else -1
    await _run_stock_tool(update, session, user, lang, tool=pager["tool"], page=pager["page"] + step)


def _import_all_models() -> None:
    """Import every model module before the first query.

    SQLAlchemy configures all mappers in the registry at once when the first
    query runs. The bot only queries a few tables, but ``Product`` references
    ``Category``/``Brand``/``Supplier`` by name, so a partial import set makes
    that first query raise ``InvalidRequestError``. Mirrors tests/conftest.py.
    """
    import app.modules.administration.models  # noqa: F401
    import app.modules.auth.models  # noqa: F401
    import app.modules.brands.models  # noqa: F401
    import app.modules.categories.models  # noqa: F401
    import app.modules.customers.models  # noqa: F401
    import app.modules.delivery.models  # noqa: F401
    import app.modules.pos.models  # noqa: F401
    import app.modules.reports.models  # noqa: F401
    import app.modules.stock.models  # noqa: F401
    import app.modules.suppliers.models  # noqa: F401
    import app.modules.telegram.models  # noqa: F401
    import app.modules.uoms.models  # noqa: F401
    import app.shared.audit.models  # noqa: F401
    import app.shared.documents.models  # noqa: F401


async def _serve(token: str) -> None:
    """Run long polling for one token until Settings changes it.

    Reply-keyboard only: no callback_query (inline) updates are processed.
    """
    from app.shared.telegram.client import resolve_bot_token
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("help", on_help))
    application.add_handler(CommandHandler("menu", on_start))
    application.add_handler(CommandHandler("link", on_link))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=["message"],
        drop_pending_updates=False,
    )
    logger.info("Telegram bot started (long polling)")

    try:
        # Pick up a token saved/changed from Administration > Settings without
        # waiting for a container restart.
        while True:
            await asyncio.sleep(_TOKEN_WATCH_SECONDS)
            if await resolve_bot_token() != token:
                logger.info("Telegram bot token changed in Settings; reloading poller")
                return
    finally:
        try:
            await application.updater.stop()
        finally:
            await application.stop()
            await application.shutdown()


async def _run_bot() -> None:
    """Supervise the poller: wait for a Settings token, then keep polling."""
    from app.shared.telegram.client import resolve_bot_token

    while True:
        token = await resolve_bot_token()
        if not token:
            logger.warning(
                "No Telegram bot token saved in Settings; retrying in %ss",
                _TOKEN_RETRY_SECONDS,
            )
            await asyncio.sleep(_TOKEN_RETRY_SECONDS)
            continue
        try:
            await _serve(token)
        except Exception:  # noqa: BLE001 - keep the container alive and retry
            logger.exception("Telegram bot poller stopped; restarting in %ss", _TOKEN_RETRY_SECONDS)
            await asyncio.sleep(_TOKEN_RETRY_SECONDS)


def run() -> None:
    # The bot runs in its own process (no FastAPI), so configure logging here:
    # without it the startup / token-reload messages are swallowed.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _import_all_models()

    # Run everything on one long-lived loop. asyncio.run() would create and
    # close its own loop, leaving pooled asyncpg/httpx connections bound to a
    # dead loop; the supervisor and the poller must share the loop the engine
    # was first used on.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_bot())
    except KeyboardInterrupt:
        pass
    finally:
        from app.shared.telegram.client import aclose_telegram_clients

        loop.run_until_complete(aclose_telegram_clients())
        loop.close()


if __name__ == "__main__":
    run()
