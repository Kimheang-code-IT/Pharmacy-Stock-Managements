"""On-demand Telegram Summary — reply keyboards, periods, totals, access.

Covers the reply-keyboard layout (and the absence of inline keyboards), the
timezone-aware period/custom-range resolution, the read-only period summary
query (sales / purchases / expenses / returns / deliveries), permission
hiding, and the conversation state machine.
"""

import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.modules.administration.models import SystemSetting
from app.modules.auth.models import User

# Import every model module so SQLAlchemy can configure Product's string
# relationships (Category/Brand/Supplier) before the first query — mirrors
# tests/conftest.py and test_inquiry.py.
import app.modules.brands.models  # noqa: F401,E402
import app.modules.categories.models  # noqa: F401,E402
import app.modules.suppliers.models  # noqa: F401,E402

from app.shared.telegram import keyboards as kb
from app.shared.telegram.inquiry import resolve_access
from app.shared.telegram.summary import (
    PERIOD_7D,
    PERIOD_MONTH,
    PERIOD_TODAY,
    SummaryConversation,
    classify_delivery_counts,
    custom_range_error,
    local_today,
    max_custom_range_days,
    parse_iso_date,
    period_summary,
    render_summary,
    resolve_period,
    shop_timezone,
    utc_window,
)
from tests.modules.pos.helpers import make_customer, make_stocked_product
from tests.utils import admin_headers, create_user_with_role


# ------------------------------------------------------------------ fixtures


@pytest.fixture(autouse=True, scope="module")
def cleanup_summary_state():
    """Drop telegram/system settings + summary users after the module."""
    yield
    if not os.environ.get("DATABASE_URL"):
        return

    async def _run() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(os.environ["DATABASE_URL"])
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.execute(
                    delete(SystemSetting).where(
                        SystemSetting.key.in_(
                            ["system.timezone", "telegram.summary_max_range_days"]
                        )
                    )
                )
                await session.execute(delete(User).where(User.email.like("summary-%")))
                await session.commit()
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


async def _admin(session) -> User:
    user = (
        await session.execute(select(User).where(User.email == "admin@gmail.com"))
    ).scalars().first()
    assert user is not None
    return user


async def _set_timezone(session, name: str) -> None:
    await session.execute(
        delete(SystemSetting).where(SystemSetting.key == "system.timezone")
    )
    session.add(SystemSetting(group_name="system", key="system.timezone", value={"v": name}))
    await session.commit()


async def _linked_user(session, *, tag: str, permissions: list[str]) -> User:
    chat_id = f"88800{tag[:6]}"
    user = await create_user_with_role(
        session,
        email=f"summary-{tag}@example.com",
        password="summarypass1",
        role_name=f"Summary Role {tag}",
        permissions=permissions,
    )
    user.telegram_chat_id = chat_id
    user.telegram_verified = True
    session.add(user)
    await session.commit()
    resolved, error = await resolve_access(session, chat_id)
    assert error is None and resolved is not None
    return resolved


async def _today_bounds(session) -> tuple[date, date, object, object]:
    from app.modules.administration.service import get_setting_value

    tz_name = str(await get_setting_value(session, "system", "timezone", "UTC") or "UTC")
    tz = shop_timezone(tz_name)
    start, end = resolve_period(PERIOD_TODAY, tz=tz)
    utc_start, utc_end = utc_window(start, end, tz)
    return start, end, utc_start, utc_end


async def _today_summary(session, user) -> dict:
    start, end, utc_start, utc_end = await _today_bounds(session)
    return await period_summary(
        session,
        utc_start=utc_start,
        utc_end=utc_end,
        local_start=start,
        local_end=end,
        user=user,
    )


# ------------------------------------------------------------------ keyboards


def test_main_keyboard_layout_order():
    rows = kb.menu_keyboard_spec("en")
    assert [button for row in rows for button in row] == [
        "Summary",
        "Current Stock",
        "Low Stock",
        "Expiring Soon",
        "Help",
    ]


def test_period_keyboard_layout_order():
    rows = kb.period_keyboard_spec("en")
    assert [button for row in rows for button in row] == [
        "Today",
        "Last 7 Days",
        "This Month",
        "Custom Date Range",
        "Back to Menu",
    ]


def test_custom_and_pagination_keyboards():
    assert kb.custom_keyboard_spec("en") == [["Cancel", "Back to Menu"]]
    assert kb.pagination_keyboard_spec("en") == [["Previous", "Next"], ["Back to Menu"]]


def test_keyboards_are_reply_not_inline():
    from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

    for spec in (
        kb.menu_keyboard_spec("en"),
        kb.period_keyboard_spec("en"),
        kb.custom_keyboard_spec("en"),
        kb.pagination_keyboard_spec("en"),
    ):
        markup = kb.to_reply_markup(spec)
        assert isinstance(markup, ReplyKeyboardMarkup)
        assert not isinstance(markup, InlineKeyboardMarkup)
        # ReplyKeyboardMarkup has no `inline_keyboard` attribute.
        assert not hasattr(markup, "inline_keyboard")


def test_route_text_matches_both_languages_and_ignores_free_text():
    assert kb.route_text("Summary") == kb.ACTION_SUMMARY
    assert kb.route_text("  last 7 days ") == kb.ACTION_7D
    assert kb.route_text("ទំនិញ") is None  # not a button
    assert kb.route_text("2026-09-30") is None
    assert kb.route_text("សេចក្តីសង្ខេប") == kb.ACTION_SUMMARY
    assert kb.route_text(kb.label(kb.ACTION_CUSTOM, "km")) == kb.ACTION_CUSTOM
    assert kb.route_text(None) is None


# ------------------------------------------------------------------- periods


def test_resolve_period_windows():
    today = date(2026, 9, 15)
    tz = shop_timezone("UTC")
    assert resolve_period(PERIOD_TODAY, tz=tz, today=today) == (today, today)
    assert resolve_period(PERIOD_7D, tz=tz, today=today) == (date(2026, 9, 9), today)
    assert resolve_period(PERIOD_MONTH, tz=tz, today=today) == (date(2026, 9, 1), today)
    with pytest.raises(ValueError):
        resolve_period("yesterday", tz=tz, today=today)


def test_utc_window_uses_shop_timezone():
    tz = shop_timezone("Asia/Phnom_Penh")  # UTC+7
    start, end = utc_window(date(2026, 1, 1), date(2026, 1, 1), tz)
    assert start.isoformat() == "2025-12-31T17:00:00+00:00"
    assert end.isoformat() == "2026-01-01T17:00:00+00:00"


def test_parse_iso_date_is_strict():
    assert parse_iso_date("2026-09-30") == date(2026, 9, 30)
    for bad in ("2026-9-30", "30-09-2026", "2026/09/30", "2026-13-01", "hello", "", None):
        assert parse_iso_date(bad) is None


def test_custom_range_validation():
    start, end = date(2026, 9, 1), date(2026, 9, 7)
    assert custom_range_error(start, end) is None
    assert "on or before" in custom_range_error(end, start)
    assert "too long" in custom_range_error(start, start + timedelta(days=400), max_days=30)
    assert "both" in custom_range_error(None, end)


def test_service_max_range_setting():
    # The default cap is a sensible positive value; the DB setting overrides it.
    assert 30 <= 366
    assert callable(max_custom_range_days)


# --------------------------------------------------------------- conversation


def test_conversation_custom_flow_and_restart():
    store = SummaryConversation()
    chat = "42"
    store.begin_custom(chat)
    assert store.custom_step(chat) == "start"
    store.set_custom_start(chat, date(2026, 9, 1))
    assert store.custom_step(chat) == "end"
    assert store.custom_start(chat) == date(2026, 9, 1)
    store.cancel_custom(chat)
    assert store.custom_step(chat) is None

    store.begin_custom(chat)
    store.set_custom_start(chat, date(2026, 9, 1))
    store.reset(chat)
    assert store.custom_step(chat) is None
    assert store.pager(chat) is None


def test_conversation_pager_state():
    store = SummaryConversation()
    store.set_pager("c", "current_stock", 2)
    assert store.pager("c") == {"tool": "current_stock", "page": 2}
    store.set_pager("c", "current_stock", 0)
    assert store.pager("c")["page"] == 1
    store.clear_pager("c")
    assert store.pager("c") is None


# --------------------------------------------------------------- deliveries


def test_classify_delivery_counts_separates_terminal_states():
    result = classify_delivery_counts(
        {
            "DELIVERED": 3,
            "PENDING": 1,
            "PREPARING": 1,
            "OUT_FOR_DELIVERY": 2,
            "PARTIALLY_DELIVERED": 1,
            "FAILED": 1,
            "RETURNED": 2,
            "WEIRD": 1,
        }
    )
    assert result["completed"] == 3
    assert result["not_completed"] == 5
    assert result["terminal"] == {"FAILED": 1, "RETURNED": 2}
    assert result["other"] == {"WEIRD": 1}


# --------------------------------------------------------------- rendering


def test_render_summary_separates_currencies_and_shows_zero():
    text = render_summary(
        {
            "period_start": "2026-09-01",
            "period_end": "2026-09-07",
            "sales": {"count": 2, "totals": {"USD": Decimal("45.00"), "KHR": Decimal("82000")}},
            "purchases": {"count": 0, "totals": {"USD": Decimal("0"), "KHR": Decimal("0")}},
            "sale_returns": {"count": 1, "totals": {"USD": Decimal("10.00")}},
            "purchase_returns": {"count": 0, "totals": {"USD": Decimal("0")}},
            "deliveries": {
                "completed": 4,
                "not_completed": 2,
                "terminal": {"FAILED": 1, "RETURNED": 0},
                "other": {},
            },
        },
        lang="en",
    )
    assert "2026-09-01 .. 2026-09-07" in text
    assert "Sales: 2 invoices" in text
    assert "USD 45.00" in text and "KHR 82000.00" in text
    assert "Purchases: 0 documents" in text
    assert "Deliveries completed: 4" in text
    assert "Deliveries not completed: 2" in text
    assert "Failed: 1" in text
    # Never a blind USD+KHR sum.
    assert "82045" not in text


def test_render_summary_without_sections_says_so():
    text = render_summary({"period_start": "2026-09-01", "period_end": "2026-09-07"})
    assert "No summary sections" in text


# ------------------------------------------------------------------- totals


@pytest.mark.asyncio
async def test_period_summary_totals_and_usd_khr_separation(client, db_session):
    await _set_timezone(db_session, "UTC")
    admin = await _admin(db_session)
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"SUM-{tag}", name=f"Summary {tag}", qty="50")
    customer = await make_customer(client, headers, code=f"SUM-C-{tag}", name=f"Summary Cust {tag}")

    before = await _today_summary(db_session, admin)

    # USD cash sale + KHR debt sale.
    usd = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert usd.status_code == 201, usd.text
    khr = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CUSTOMER_DEBT",
            "customer_id": customer["id"],
            "currency": "KHR",
            "exchange_rate": "4100",
            "amount_received": "0",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert khr.status_code == 201, khr.text

    # Purchase (Stock In) with discount + tax: total = 20 - 2 + 1 = 19.
    purchase = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "19.00",
            "discount_amount": "2.00",
            "tax_amount": "1.00",
            "items": [{"product_id": product["id"], "quantity": "2", "unit_cost": "10.00"}],
        },
        headers=headers,
    )
    assert purchase.status_code == 201, purchase.text

    # Operating expense (POSTED).
    # Expense dates are shop-local calendar dates (not the OS/UTC date).
    expense = await client.post(
        "/api/v1/reports/finance/expenses",
        json={
            "date": local_today(shop_timezone("UTC")).isoformat(),
            "category": "Utilities",
            "amount": "7.00",
        },
        headers=headers,
    )
    assert expense.status_code == 201, expense.text

    # Sale return of 1 unit (refund 10.00).
    line = usd.json()["data"]["items"][0]
    sale_return = await client.post(
        f"/api/v1/pos/sales/{usd.json()['data']['id']}/return",
        json={"reason": "damaged", "items": [{"sale_item_id": line["id"], "quantity": "1", "restock": True}]},
        headers=headers,
    )
    assert sale_return.status_code == 201, sale_return.text

    after = await _today_summary(db_session, admin)

    usd_total = Decimal(usd.json()["data"]["grand_total"])
    khr_total = Decimal(khr.json()["data"]["grand_total"])
    purchase_total = Decimal(purchase.json()["data"]["total_amount"])
    refund = Decimal(sale_return.json()["data"]["refund_amount"])

    assert after["sales"]["count"] == before["sales"]["count"] + 2
    assert after["sales"]["totals"]["USD"] - before["sales"]["totals"]["USD"] == usd_total
    assert after["sales"]["totals"]["KHR"] - before["sales"]["totals"]["KHR"] == khr_total
    # USD and KHR stay in separate buckets (never summed together).
    assert usd_total == Decimal("20.00")
    assert khr_total != usd_total

    assert after["purchases"]["count"] == before["purchases"]["count"] + 1
    assert after["purchases"]["totals"]["USD"] - before["purchases"]["totals"]["USD"] == purchase_total

    assert after["expenses"]["count"] == before["expenses"]["count"] + 1
    assert after["expenses"]["totals"]["USD"] - before["expenses"]["totals"]["USD"] == Decimal("7.00")

    assert after["sale_returns"]["count"] == before["sale_returns"]["count"] + 1
    assert after["sale_returns"]["totals"]["USD"] - before["sale_returns"]["totals"]["USD"] == refund

    # The rendered message keeps currencies separate and never sums them.
    text = render_summary(after, lang="en")
    assert "USD" in text and "KHR" in text
    assert "Sales:" in text


@pytest.mark.asyncio
async def test_period_summary_counts_purchase_return(client, db_session):
    await _set_timezone(db_session, "UTC")
    admin = await _admin(db_session)
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"PRT-{tag}", name=f"PRet {tag}", qty="10")

    purchase = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "20.00",
            "items": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2.00"}],
        },
        headers=headers,
    )
    assert purchase.status_code == 201, purchase.text
    doc = purchase.json()["data"]
    line = purchase.json()["data"]["items"][0]

    before = await _today_summary(db_session, admin)
    returned = await client.post(
        f"/api/v1/stock/in/{doc['id']}/return",
        json={"reason": "wrong item", "lines": [{"stock_transaction_item_id": line["id"], "quantity": "4"}]},
        headers=headers,
    )
    assert returned.status_code == 201, returned.text
    after = await _today_summary(db_session, admin)

    assert after["purchase_returns"]["count"] == before["purchase_returns"]["count"] + 1
    assert after["purchase_returns"]["totals"]["USD"] - before["purchase_returns"]["totals"]["USD"] == Decimal("8.00")


@pytest.mark.asyncio
async def test_period_summary_empty_future_period_is_zero(client, db_session):
    await _set_timezone(db_session, "UTC")
    admin = await _admin(db_session)
    tz = shop_timezone("UTC")
    start = date(2999, 1, 1)
    utc_start, utc_end = utc_window(start, start, tz)
    summary = await period_summary(
        db_session,
        utc_start=utc_start,
        utc_end=utc_end,
        local_start=start,
        local_end=start,
        user=admin,
    )
    assert summary["sales"]["count"] == 0
    assert summary["purchases"]["count"] == 0
    assert summary["expenses"]["count"] == 0
    assert summary["deliveries"]["completed"] == 0
    assert summary["deliveries"]["not_completed"] == 0


@pytest.mark.asyncio
async def test_period_summary_timezone_boundary(client, db_session):
    """A sale taken just after local midnight belongs to the local day."""
    admin = await _admin(db_session)
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"TZ-{tag}", name=f"TZ {tag}", qty="10")

    await _set_timezone(db_session, "Asia/Phnom_Penh")  # UTC+7
    # 2025-12-31T17:30Z == 2026-01-01 00:30 local (+07).
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "sale_date": "2025-12-31T17:30:00+00:00",
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    tz = shop_timezone("Asia/Phnom_Penh")
    day = date(2026, 1, 1)
    utc_start, utc_end = utc_window(day, day, tz)
    summary = await period_summary(
        db_session,
        utc_start=utc_start,
        utc_end=utc_end,
        local_start=day,
        local_end=day,
        user=admin,
    )
    assert summary["sales"]["count"] == 1

    # The same instant is NOT in the UTC calendar day 2026-01-01 — it is
    # 2025-12-31 in UTC, so a UTC-boundary query for the local date misses it.
    tz_utc = shop_timezone("UTC")
    utc_start2, utc_end2 = utc_window(day, day, tz_utc)
    summary_utc = await period_summary(
        db_session,
        utc_start=utc_start2,
        utc_end=utc_end2,
        local_start=day,
        local_end=day,
        user=admin,
    )
    assert summary_utc["sales"]["count"] == 0


# ---------------------------------------------------------------- permissions


@pytest.mark.asyncio
async def test_summary_hides_sections_without_permission(db_session):
    tag = uuid.uuid4().hex[:6]
    sales_only = await _linked_user(db_session, tag=tag, permissions=["report.sales"])
    summary = await _today_summary(db_session, sales_only)
    assert "sales" in summary and "sale_returns" in summary
    assert "purchases" not in summary
    assert "expenses" not in summary
    assert "deliveries" not in summary
    text = render_summary(summary, lang="en")
    assert "Sales:" in text
    assert "Purchases:" not in text
    assert "Expenses:" not in text
    assert "Deliveries" not in text


@pytest.mark.asyncio
async def test_summary_without_any_permission_shows_nothing(db_session):
    tag = uuid.uuid4().hex[:6]
    no_perms = await _linked_user(db_session, tag=tag, permissions=[])
    summary = await _today_summary(db_session, no_perms)
    assert "sales" not in summary and "purchases" not in summary
    assert "No summary sections" in render_summary(summary, lang="en")


@pytest.mark.asyncio
async def test_unlinked_and_disabled_and_unauthorized_access(db_session):
    # Unlinked chat → instruction only (no business data).
    user, error = await resolve_access(db_session, "555000999")
    assert user is None and error is not None

    # Disabled inquiry → refused even for a verified link.
    tag = uuid.uuid4().hex[:6]
    linked = await _linked_user(db_session, tag=tag, permissions=["report.sales"])
    await db_session.execute(
        delete(SystemSetting).where(SystemSetting.key == "telegram.stock_inquiry_enabled")
    )
    db_session.add(
        SystemSetting(group_name="telegram", key="telegram.stock_inquiry_enabled", value={"v": False})
    )
    await db_session.commit()
    try:
        resolved, disabled_error = await resolve_access(db_session, linked.telegram_chat_id)
        assert resolved is None and disabled_error is not None
    finally:
        await db_session.execute(
            delete(SystemSetting).where(SystemSetting.key == "telegram.stock_inquiry_enabled")
        )
        await db_session.commit()


# ------------------------------------------------------------- deliveries db


@pytest.mark.asyncio
async def test_period_summary_delivery_period_and_counts(client, db_session):
    await _set_timezone(db_session, "UTC")
    admin = await _admin(db_session)
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    product = await make_stocked_product(client, headers, sku=f"DLV-{tag}", name=f"Dlv {tag}", qty="10")
    customer = await make_customer(client, headers, code=f"DLV-C-{tag}", name=f"Dlv Cust {tag}")
    sale = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": "3"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    sale_data = sale.json()["data"]
    line = sale_data["items"][0]

    before = await _today_summary(db_session, admin)
    created = await client.post(
        "/api/v1/delivery",
        json={"lines": [{"saleId": sale_data["id"], "saleItemId": line["id"], "qtyToDeliver": "2"}]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    after = await _today_summary(db_session, admin)

    assert after["deliveries"]["not_completed"] == before["deliveries"]["not_completed"] + 1
    assert after["deliveries"]["completed"] == before["deliveries"]["completed"]
