"""Telegram expiry alert tests — spec sections 3.6 + telegram_expiry_alert_state.

Covers: dedupe per lot/level, independent alert windows, disabled toggle,
only qty>0 expiry-tracked lots, recipients, message content, and the
Settings GET/PATCH surface (bot token stays env-only).
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.auth.models import Role, User
from app.modules.administration.repository import SettingsRepository
from app.modules.telegram.models import TelegramExpiryAlertState
from app.modules.telegram.service import ExpiryAlertService
from tests.utils import DEFAULT_UOM_ID, admin_headers, login


class FakeSender:
    """Records (chat_id, text) sends; always succeeds."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, chat_id: str, text: str) -> bool:
        self.calls.append((chat_id, text))
        return True


async def set_setting(db_session, group: str, key: str, value) -> None:
    await SettingsRepository(db_session).upsert(group, f"{group}.{key}", value, is_secret=False, updated_by=None)
    await db_session.commit()


async def make_verified_telegram_user(db_session, tag: str) -> User:
    role_id = await db_session.scalar(select(Role.id).where(Role.name == "Administrator"))
    user = User(
        full_name=f"TG User {tag}",
        email=f"tg-{tag}@example.com",
        password_hash="not-a-real-hash",
        telegram_chat_id=f"100{tag[:6]}",
        telegram_verified=True,
        role_id=role_id,
        status="ACTIVE",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def make_expiry_lot(client, headers, *, tag: str, sku: str, expiry_date: str, qty: str = "5", batch: str | None = "B1", expiry_tracking: bool = True) -> dict:
    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"TEA-{tag}", "name": f"Tea Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    payload = {
        "sku": sku,
        "name": f"Expiry Widget {tag}",
        "category_id": category["id"],
        "uom_id": str(DEFAULT_UOM_ID),
        "selling_price": "2.00",
        "expiry_tracking": expiry_tracking,
    }
    product = (
        await client.post("/api/v1/products", json=payload, headers=headers)
    ).json()["data"]
    item: dict = {"product_id": product["id"], "quantity": qty, "unit_cost": "1.00"}
    if batch is not None:
        item["batch_no"] = batch
    if expiry_tracking:
        item["expiry_date"] = expiry_date
    stock_in = await client.post(
        "/api/v1/stock/in",
        json={
            "paid_amount": str(Decimal(qty)),  # fully paid at unit_cost 1.00
            "items": [item],
        },
        headers=headers,
    )
    assert stock_in.status_code == 201, stock_in.text
    return product


async def state_rows(db_session, product_id) -> list[TelegramExpiryAlertState]:
    result = await db_session.execute(
        select(TelegramExpiryAlertState).where(TelegramExpiryAlertState.product_id == product_id)
    )
    return list(result.scalars().all())


def messages_for(sender: FakeSender, sku: str) -> list[str]:
    # One text per (lot, alert level); every recipient gets a copy, so dedupe.
    return sorted({text for _chat, text in sender.calls if sku in text})


@pytest.fixture
async def alert_settings(db_session):
    """Explicit windows: 90 / 7, alerts enabled."""
    await set_setting(db_session, "stock", "expiry_alert_1_days", 90)
    await set_setting(db_session, "stock", "expiry_alert_2_days", 7)
    await set_setting(db_session, "telegram", "expiry_alerts_enabled", True)


@pytest.mark.asyncio
async def test_both_levels_fire_once_per_lot(client, db_session, alert_settings):
    tag = uuid.uuid4().hex[:8]
    await make_verified_telegram_user(db_session, tag)
    today = date.today()
    product = await make_expiry_lot(
        client, await admin_headers(client), tag=tag, sku=f"EXP-{tag}",
        expiry_date=(today + timedelta(days=5)).isoformat(), qty="5", batch="B-EXP",
    )

    first = FakeSender()
    summary = await ExpiryAlertService(db_session).scan_and_send(sender=first, today=today)
    assert summary["enabled"] is True

    # Expiry in 5 days is within both windows (90 and 7): both levels fire.
    level1 = [t for t in messages_for(first, f"EXP-{tag}") if "Alert 1" in t]
    level2 = [t for t in messages_for(first, f"EXP-{tag}") if "Alert 2" in t]
    assert len(level1) == 1
    assert len(level2) == 1
    rows = await state_rows(db_session, product["id"])
    assert {(r.alert_level) for r in rows} == {1, 2}

    # Message content: name, sku, batch, expiry date, qty, level.
    text = level1[0]
    assert f"Expiry Widget {tag}" in text
    assert f"EXP-{tag}" in text
    assert "Batch: B-EXP" in text
    assert (today + timedelta(days=5)).isoformat() in text
    assert "5" in text  # remaining qty

    # Second run on the same day: dedupe — no new sends.
    second = FakeSender()
    summary2 = await ExpiryAlertService(db_session).scan_and_send(sender=second, today=today)
    assert messages_for(second, f"EXP-{tag}") == []
    assert summary2["sent"] == 0
    assert len(await state_rows(db_session, product["id"])) == 2


@pytest.mark.asyncio
async def test_alert_levels_are_independent_windows(client, db_session, alert_settings):
    tag = uuid.uuid4().hex[:8]
    await make_verified_telegram_user(db_session, tag)
    today = date.today()
    product = await make_expiry_lot(
        client, await admin_headers(client), tag=tag, sku=f"WIN-{tag}",
        expiry_date=(today + timedelta(days=60)).isoformat(), qty="4", batch=None,
    )

    first = FakeSender()
    await ExpiryAlertService(db_session).scan_and_send(sender=first, today=today)

    # 60 days out: inside Alert 1 (90), outside Alert 2 (7). Unbatched lot dedupes too.
    assert len(messages_for(first, f"WIN-{tag}")) == 1
    assert "Alert 1" in messages_for(first, f"WIN-{tag}")[0]
    rows = await state_rows(db_session, product["id"])
    assert [r.alert_level for r in rows] == [1]
    assert rows[0].batch_no is None

    # Tightening Alert 2 to 70 days makes the lot enter window 2 on the next run.
    await set_setting(db_session, "stock", "expiry_alert_2_days", 70)
    second = FakeSender()
    await ExpiryAlertService(db_session).scan_and_send(sender=second, today=today)
    win_messages = messages_for(second, f"WIN-{tag}")
    assert len(win_messages) == 1
    assert "Alert 2" in win_messages[0]
    assert len(await state_rows(db_session, product["id"])) == 2


@pytest.mark.asyncio
async def test_disabled_setting_skips_send(client, db_session, alert_settings):
    tag = uuid.uuid4().hex[:8]
    await make_verified_telegram_user(db_session, tag)
    today = date.today()
    product = await make_expiry_lot(
        client, await admin_headers(client), tag=tag, sku=f"DIS-{tag}",
        expiry_date=(today + timedelta(days=3)).isoformat(), qty="2", batch="B-DIS",
    )
    await set_setting(db_session, "telegram", "expiry_alerts_enabled", False)

    sender = FakeSender()
    summary = await ExpiryAlertService(db_session).scan_and_send(sender=sender, today=today)
    assert summary["enabled"] is False
    assert sender.calls == []
    assert await state_rows(db_session, product["id"]) == []

    # Re-enabling lets the sweep run again (nothing was suppressed).
    await set_setting(db_session, "telegram", "expiry_alerts_enabled", True)
    enabled_sender = FakeSender()
    summary = await ExpiryAlertService(db_session).scan_and_send(sender=enabled_sender, today=today)
    assert summary["enabled"] is True
    assert len(messages_for(enabled_sender, f"DIS-{tag}")) == 2  # both levels


@pytest.mark.asyncio
async def test_only_positive_qty_expiry_tracked_lots_alert(client, db_session, alert_settings):
    tag = uuid.uuid4().hex[:8]
    await make_verified_telegram_user(db_session, tag)
    headers = await admin_headers(client)
    today = date.today()
    soon = (today + timedelta(days=5)).isoformat()  # inside both windows (90/7)

    # In-stock lot: alerts.
    in_stock = await make_expiry_lot(
        client, headers, tag=tag + "a", sku=f"POS-{tag}", expiry_date=soon, qty="5", batch="B-OK"
    )
    # Fully expired lot: remaining qty 0 -> must not alert.
    emptied = await make_expiry_lot(
        client, headers, tag=tag + "b", sku=f"EMP-{tag}", expiry_date=soon, qty="3", batch="B-EMPTY"
    )
    expire = await client.post(
        "/api/v1/stock/expire",
        json={
            "items": [
                {
                    "product_id": emptied["id"],
                    "quantity": "3",
                    "batch_no": "B-EMPTY",
                    "expiry_date": soon,
                }
            ]
        },
        headers=headers,
    )
    assert expire.status_code == 201, expire.text

    # Expiry-untracked product: excluded even with batched/expiry-dated stock.
    untracked = await make_expiry_lot(
        client, headers, tag=tag + "c", sku=f"UNT-{tag}", expiry_date=soon, qty="7",
        batch="B-UNT", expiry_tracking=False,
    )

    sender = FakeSender()
    await ExpiryAlertService(db_session).scan_and_send(sender=sender, today=today)

    assert len(messages_for(sender, f"POS-{tag}")) == 2  # both levels
    assert messages_for(sender, f"EMP-{tag}") == []
    assert messages_for(sender, f"UNT-{tag}") == []
    assert await state_rows(db_session, in_stock["id"])
    assert await state_rows(db_session, emptied["id"]) == []
    assert await state_rows(db_session, untracked["id"]) == []


@pytest.mark.asyncio
async def test_failed_delivery_records_nothing_and_retries(client, db_session, alert_settings):
    """No state row when nothing was delivered: the next sweep retries."""
    tag = uuid.uuid4().hex[:8]
    await make_verified_telegram_user(db_session, tag)
    today = date.today()
    product = await make_expiry_lot(
        client, await admin_headers(client), tag=tag, sku=f"NR-{tag}",
        expiry_date=(today + timedelta(days=2)).isoformat(), qty="2", batch="B-NR",
    )

    class FailingSender:
        async def __call__(self, chat_id: str, text: str) -> bool:
            return False

    await ExpiryAlertService(db_session).scan_and_send(sender=FailingSender(), today=today)
    assert await state_rows(db_session, product["id"]) == []

    # A healthy sender on the next sweep delivers both levels and records state.
    second = FakeSender()
    summary = await ExpiryAlertService(db_session).scan_and_send(sender=second, today=today)
    assert len(messages_for(second, f"NR-{tag}")) == 2
    assert all(chat_id.startswith("100") for chat_id, _t in second.calls)
    assert len(await state_rows(db_session, product["id"])) == 2
    assert summary["levels"] == {1: 1, 2: 1}


@pytest.mark.asyncio
async def test_settings_surface_and_env_only_bot_token(client):
    headers = await admin_headers(client)
    current = await client.get("/api/v1/admin/settings", headers=headers)
    assert current.status_code == 200
    groups = current.json()["data"]["groups"]
    assert groups["stock"]["expiry_alert_1_days"] == 90
    assert groups["stock"]["expiry_alert_2_days"] == 7
    assert groups["telegram"]["expiry_alerts_enabled"] is True

    patched = await client.patch(
        "/api/v1/admin/settings",
        json={
            "values": {
                "stock": {"expiry_alert_1_days": 45, "expiry_alert_2_days": 10},
                "telegram": {"expiry_alerts_enabled": False},
            }
        },
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    values = patched.json()["data"]["groups"]
    assert values["stock"]["expiry_alert_1_days"] == 45
    assert values["stock"]["expiry_alert_2_days"] == 10
    assert values["telegram"]["expiry_alerts_enabled"] is False

    # The bot token never persists to the DB: writes are rejected.
    token_write = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"telegram": {"bot_token": "123456:ABC-DEF"}}},
        headers=headers,
    )
    assert token_write.status_code == 422
    assert "environment" in token_write.json()["detail"]["message"].lower()

    # Restore defaults for later suites.
    restored = await client.patch(
        "/api/v1/admin/settings",
        json={
            "values": {
                "stock": {"expiry_alert_1_days": 90, "expiry_alert_2_days": 7},
                "telegram": {"expiry_alerts_enabled": True},
            }
        },
        headers=headers,
    )
    assert restored.status_code == 200


@pytest.mark.asyncio
async def test_in_process_scheduler_computes_next_scan(client):
    """Expiry sweep is scheduled inside the API process, not Celery beat."""
    from datetime import datetime, timezone

    from app.core.scheduler import seconds_until_next_scan

    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    wait = seconds_until_next_scan(now)
    assert wait == 3600.0
