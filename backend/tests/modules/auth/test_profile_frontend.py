"""Auth profile & frontend contract: camelCase token payloads, avatar,
change-password, Telegram link codes and the reset handoff exchange."""

import pytest

from tests.modules.auth.test_reset import ADMIN_EMAIL, admin_with_chat_id, captured_deliveries
from tests.utils import admin_headers, login


@pytest.fixture(autouse=True)
async def restore_admin_state():
    """Password tests mutate the seeded admin; restore identity state after."""
    from sqlalchemy import select

    from app.core.database import SessionFactory
    from app.modules.auth.models import User

    async with SessionFactory() as session:
        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        snapshot = (admin.password_hash, admin.token_version, admin.telegram_chat_id, admin.telegram_verified)
    yield
    async with SessionFactory() as session:
        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        admin.password_hash, admin.token_version, admin.telegram_chat_id, admin.telegram_verified = snapshot
        await session.commit()


@pytest.mark.asyncio
async def test_login_returns_camel_case_token_payload(client):
    data = await login(client, "admin@gmail.com", "123456")
    # Both spellings are present: legacy tests use snake_case, the SPA uses camelCase.
    assert data["access_token"] == data["accessToken"]
    assert data["refresh_token"] == data["refreshToken"]
    assert data["expires_in"] == data["expiresIn"]
    user = data["user"]
    assert user["name"] == user["full_name"]
    assert isinstance(user["effectivePermissions"], list) and user["effectivePermissions"]
    assert user["telegramLinked"] is bool(user["telegram_verified"] and user["telegram_chat_id"])


@pytest.mark.asyncio
async def test_me_exposes_spa_profile_keys(client):
    headers = await admin_headers(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    data = me.json()["data"]
    assert data["email"] == "admin@gmail.com"
    assert data["name"]
    assert data["effectivePermissions"] == data["permissions"]


@pytest.mark.asyncio
async def test_profile_avatar_set_and_clear(client):
    headers = await admin_headers(client)
    avatar = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
    updated = await client.patch(
        "/api/v1/auth/profile/avatar", json={"avatar": avatar}, headers=headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["avatar"] == avatar

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["data"]["avatar"] == avatar

    cleared = await client.patch("/api/v1/auth/profile/avatar", json={"avatar": None}, headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["avatar"] is None


@pytest.mark.asyncio
async def test_change_password_round_trip(client):
    data = await login(client, "admin@gmail.com", "123456")
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "nope-wrong", "newPassword": "new-secret-99"},
        headers=headers,
    )
    assert wrong.status_code == 422

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "123456", "newPassword": "new-secret-99"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    # Old tokens are signed out (token version bumped); the new password works.
    old_token = await client.get("/api/v1/auth/me", headers=headers)
    assert old_token.status_code == 401
    relogin = await login(client, "admin@gmail.com", "new-secret-99")
    assert relogin["accessToken"]


@pytest.mark.asyncio
async def test_telegram_link_code_is_one_time(client, db_session):
    headers = await admin_headers(client)
    created = await client.post("/api/v1/auth/telegram/link-code", headers=headers)
    assert created.status_code == 200, created.text
    body = created.json()["data"]
    assert len(body["code"]) == 8
    assert body["expiresIn"] == body["expires_in"] > 0

    # The code can be consumed exactly once by the bot's /link flow.
    from app.shared.telegram.linking import consume_link_code

    linked = await consume_link_code(db_session, body["code"], "900001111")
    assert linked is not None
    assert linked.telegram_verified is True

    again = await consume_link_code(db_session, body["code"], "900001111")
    assert again is None


@pytest.mark.asyncio
async def test_handoff_exchange_issues_single_use_reset_session(client, admin_with_chat_id, captured_deliveries):
    requested = await client.post("/api/v1/auth/forgot-password", json={"email": ADMIN_EMAIL})
    assert requested.status_code == 200
    assert captured_deliveries, "reset code queued"

    # The handoff token travels with the queued delivery.
    handoff_token = captured_deliveries[-1][2]
    assert handoff_token

    exchanged = await client.post(
        "/api/v1/auth/forgot-password/handoff", json={"handoff": handoff_token}
    )
    assert exchanged.status_code == 200, exchanged.text
    data = exchanged.json()["data"]
    assert data["email"] == ADMIN_EMAIL
    assert data["resetToken"] == data["reset_token"]

    # Single use: a second exchange with the same token fails.
    replay = await client.post(
        "/api/v1/auth/forgot-password/handoff", json={"handoff": handoff_token}
    )
    assert replay.status_code == 422

    # The issued reset token completes the flow.
    new_password = "handoff-pass-1"
    reset = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"email": ADMIN_EMAIL, "resetToken": data["resetToken"], "newPassword": new_password},
    )
    assert reset.status_code == 200, reset.text
    relogin = await login(client, ADMIN_EMAIL, new_password)
    assert relogin["accessToken"]


@pytest.mark.asyncio
async def test_handoff_rejects_unknown_token(client):
    response = await client.post(
        "/api/v1/auth/forgot-password/handoff", json={"handoff": "totally-unknown-token-value"}
    )
    assert response.status_code == 422
