"""View-only Telegram stock inquiry tests — spec sections 3.6 / 3.6.1.

Covers: linked vs unlinked vs disabled access, each read-only tool returning
read data from canonical tables, and refusal of write-shaped callbacks
("View only"). Password-reset delivery is unaffected (it does not go through
the inquiry access gate).
"""

import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.auth.models import Role, User
from app.modules.administration.repository import SettingsRepository
# Import Brand/Category models so configure_mappers() (triggered by the
# cleanup fixture's delete) resolves Product's string relationships even
# when the session-scoped DB setup has not run yet.
import app.modules.brands.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
from app.shared.telegram.inquiry import (
    DISABLED_REPLY,
    UNLINKED_REPLY,
    VIEW_ONLY_REPLY,
    InquiryAction,
    period_bounds,
    render_page,
    resolve_access,
    route_callback,
    run_tool,
)
from tests.modules.pos.helpers import make_stocked_product
from tests.utils import DEFAULT_UOM_ID, admin_headers


async def set_setting(db_session, group: str, key: str, value) -> None:
    await SettingsRepository(db_session).upsert(
        group, f"{group}.{key}", value, is_secret=False, updated_by=None
    )
    await db_session.commit()


@pytest.fixture(autouse=True)
def cleanup_telegram_users():
    """Remove inquiry-created Telegram users after each test.

    Tests share one database with no per-test rollback; verified Telegram
    users left behind would otherwise become expiry-alert recipients in
    tests/modules/telegram (which assert only their own users receive
    messages). Runs on its own event loop/engine so it works for sync and
    async tests alike.
    """
    yield
    from sqlalchemy import delete

    async def _run() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(os.environ["DATABASE_URL"])
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.execute(delete(User).where(User.email.like("inquiry-%")))
                await session.commit()
        finally:
            await engine.dispose()

    # Do NOT use asyncio.run(): it sets the thread's current event loop to
    # None on exit, which breaks pytest-asyncio's loop handling for any
    # subsequent async tests in the session.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


async def make_telegram_user(db_session, tag: str, *, verified: bool = True) -> User:
    role_id = await db_session.scalar(select(Role.id).where(Role.name == "Administrator"))
    user = User(
        full_name=f"Inquiry User {tag}",
        email=f"inquiry-{tag}@example.com",
        password_hash="not-a-real-hash",
        telegram_chat_id=f"777000{tag[:6]}",
        telegram_verified=verified,
        role_id=role_id,
        status="ACTIVE",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def make_expiry_lot(client, headers, *, tag: str, sku: str, expiry_date: str, qty: str = "5") -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"TI-{tag}", "name": f"Inquiry Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": sku,
                "name": f"Inquiry Widget {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "2.00",
                "expiry_tracking": True,
            },
            headers=headers,
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": str(int(qty)),  # unit_cost 1.00
            "items": [{"product_id": product["id"], "quantity": qty, "unit_cost": "1.00", "expiry_date": expiry_date}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    return product


# ------------------------------------------------------------ callback routing


def test_route_callback_allows_only_read_actions():
    assert route_callback("menu") == InquiryAction(tool="menu")
    assert route_callback("help") == InquiryAction(tool="help")
    assert route_callback("tool:current_stock") == InquiryAction(tool="current_stock")
    assert route_callback("tool:sales") == InquiryAction(tool="sales")
    assert route_callback("page:sales:month:2") == InquiryAction(tool="sales", period="month", page=2)
    assert route_callback("page:current_stock:-:3") == InquiryAction(tool="current_stock", page=3)


def test_write_shaped_callbacks_are_refused():
    # Any non-whitelisted payload — including write-shaped ones — is refused.
    for payload in (
        "stock:adjust",
        "stock_in:create",
        "stock:damage",
        "stock:expire",
        "sale:create",
        "payment:record",
        "debt_payment:create",
        "settings:update",
        "user:delete",
        "tool:stock_in",
        "tool:sales:today",  # malformed shape
        "page:sales:yesterday:1",  # unknown period
        "page:current_stock:-:notanumber",
        "page:current_stock:-:99999",  # page out of sane bounds
        "random",
        "",
        None,
    ):
        assert route_callback(payload) is None, payload


# -------------------------------------------------------------------- access


@pytest.mark.asyncio
async def test_unlinked_chat_gets_instruction_only(client, db_session):
    tag = uuid.uuid4().hex[:8]
    # Seed business data that must NOT leak to the unlinked chat.
    await make_stocked_product(client, await admin_headers(client), sku=f"UNL-{tag}", name=f"Unlinked {tag}")

    user, error = await resolve_access(db_session, "999000123")
    assert user is None
    assert error is not None
    assert "999000123" in error  # the chat id so the admin can link it
    assert "not linked" in error.lower() or "Chat ID" in error
    assert f"Unlinked {tag}" not in error  # no business data


@pytest.mark.asyncio
async def test_linked_verified_user_is_allowed(client, db_session):
    tag = uuid.uuid4().hex[:8]
    user = await make_telegram_user(db_session, tag, verified=True)
    resolved, error = await resolve_access(db_session, user.telegram_chat_id)
    assert error is None
    assert resolved is not None and resolved.id == user.id


@pytest.mark.asyncio
async def test_unverified_chat_id_is_refused(client, db_session):
    tag = uuid.uuid4().hex[:8]
    user = await make_telegram_user(db_session, tag, verified=False)
    resolved, error = await resolve_access(db_session, user.telegram_chat_id)
    # A chat id stored but not verified is treated as unlinked (same gate the
    # expiry alert recipients use) — instruction only, no business data.
    assert resolved is None
    assert error == UNLINKED_REPLY.format(chat_id=user.telegram_chat_id)


@pytest.mark.asyncio
async def test_disabled_setting_refuses_inquiry(client, db_session):
    tag = uuid.uuid4().hex[:8]
    user = await make_telegram_user(db_session, tag, verified=True)
    await set_setting(db_session, "telegram", "stock_inquiry_enabled", False)
    try:
        resolved, error = await resolve_access(db_session, user.telegram_chat_id)
        assert resolved is None
        assert error == DISABLED_REPLY
    finally:
        await set_setting(db_session, "telegram", "stock_inquiry_enabled", True)


# --------------------------------------------------------------------- tools


@pytest.mark.asyncio
async def test_current_stock_returns_read_data(client, db_session):
    tag = uuid.uuid4().hex[:8]
    await make_stocked_product(
        client, await admin_headers(client), sku=f"CUR-{tag}", name=f"Current {tag}", qty="7"
    )
    text, total_pages = await run_tool(db_session, InquiryAction(tool="current_stock"))
    assert f"Current {tag}" in text
    assert f"CUR-{tag}" in text
    assert "7" in text
    assert total_pages >= 1


@pytest.mark.asyncio
async def test_low_stock_lists_products_at_or_below_minimum(client, db_session):
    tag = uuid.uuid4().hex[:8]
    headers = await admin_headers(client)
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"LOW-{tag}", "name": f"Low Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"LOW-{tag}",
                "name": f"Low Widget {tag}",
                "category_id": category["id"],
                "uom_id": str(DEFAULT_UOM_ID),
                "selling_price": "2.00",
                "minimum_stock": "10",
            },
            headers=headers,
        )
    ).json()["data"]
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": "3.00",
            "items": [{"product_id": product["id"], "quantity": "3", "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text

    text, _ = await run_tool(db_session, InquiryAction(tool="low_stock"))
    assert f"Low Widget {tag}" in text
    assert "LOW" in text


@pytest.mark.asyncio
async def test_expiring_uses_settings_alert_windows(client, db_session):
    tag = uuid.uuid4().hex[:8]
    headers = await admin_headers(client)
    await set_setting(db_session, "stock", "expiry_alert_1_days", 90)
    await set_setting(db_session, "stock", "expiry_alert_2_days", 7)
    today = date.today()
    # Inside Alert 2 window (<= 7 days) and inside Alert 1 window.
    soon = await make_expiry_lot(
        client, headers, tag=f"a{tag}", sku=f"EXP2-{tag}", expiry_date=(today + timedelta(days=5)).isoformat()
    )
    # Inside Alert 1 but outside Alert 2 (45 days out).
    mid = await make_expiry_lot(
        client, headers, tag=f"b{tag}", sku=f"EXP1-{tag}", expiry_date=(today + timedelta(days=45)).isoformat()
    )
    # Outside both windows (200 days out).
    await make_expiry_lot(
        client, headers, tag=f"c{tag}", sku=f"EXP0-{tag}", expiry_date=(today + timedelta(days=200)).isoformat()
    )

    text, _ = await run_tool(db_session, InquiryAction(tool="expiring"))
    assert f"EXP2-{tag}" in text
    assert "ALERT 2" in text
    assert f"EXP1-{tag}" in text
    assert "ALERT 1" in text
    assert f"EXP0-{tag}" not in text  # outside the configured windows
    assert "Alert 1 = 90d" in text and "Alert 2 = 7d" in text
    assert soon["sku"] and mid["sku"]


@pytest.mark.asyncio
async def test_sales_summary_period_totals(client, db_session):
    tag = uuid.uuid4().hex[:8]
    headers = await admin_headers(client)

    def totals(text: str) -> tuple[int, Decimal]:
        count = int(next(line for line in text.splitlines() if line.startswith("Invoices:")).split(":")[1])
        gross = Decimal(
            next(line for line in text.splitlines() if line.startswith("Gross sales:")).split(":")[1].strip()
        )
        return count, gross

    before, _ = await run_tool(db_session, InquiryAction(tool="sales", period="today"))
    before_count, before_gross = totals(before)

    product = await make_stocked_product(client, headers, sku=f"SAL-{tag}", name=f"Sale {tag}", qty="10")
    response = await client.post(
        "/api/v1/pos/sales",
        json={
            "payment_method": "CASH",
            "amount_received": "100.00",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    sale = response.json()["data"]

    text, _ = await run_tool(db_session, InquiryAction(tool="sales", period="today"))
    after_count, after_gross = totals(text)
    assert after_count == before_count + 1
    # The period total includes the new invoice (delta instead of a fragile
    # substring check against the shared test database).
    assert after_gross - before_gross == Decimal(sale["grand_total"])


@pytest.mark.asyncio
async def test_sales_summary_requires_period():
    from app.shared.telegram.inquiry import PAGE_SIZE, render_page

    # The bot only runs the sales tool after a period selection; the period
    # keyboards produce page:sales:<period>:1 callbacks (see routing tests).
    text, pages = render_page("Sales Summary", ["Invoices: 1"], 1, 1, page_size=PAGE_SIZE)
    assert "Invoices: 1" in text and pages == 1


# ---------------------------------------------------------------- pagination


def test_period_bounds_windows():
    start, end = period_bounds("today")
    assert start < end and (end - start).days == 1
    start, end = period_bounds("7d")
    assert (end - start).days == 7
    start, end = period_bounds("month")
    assert start.day == 1 and start < end
    with pytest.raises(ValueError):
        period_bounds("yesterday")


def test_render_page_caps_and_paginates():
    lines = [f"item {i}" for i in range(40)]
    text, pages = render_page("Current Stock", lines, page=2, total=40, page_size=15)
    assert "page 2/3" in text and "item 15" in text and "item 40" not in text
    assert pages == 3


def test_view_only_reply_constant():
    assert VIEW_ONLY_REPLY == "View only"
