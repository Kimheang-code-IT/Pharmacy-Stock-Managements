"""Security settings enforcement (spec: Phase 3).

Password expiry / forced change, DB-backed lockout that survives Redis being
unavailable, immediate loss of access for disabled users and disabled roles, and
token invalidation after a role change.
"""

import uuid
from datetime import timedelta

import pytest

from app.core.security import utcnow
from tests.utils import admin_headers, create_user_with_role, login


class _BrokenRedis:
    async def exists(self, *args, **kwargs):
        raise RuntimeError("redis unavailable")

    async def incr(self, *args, **kwargs):
        raise RuntimeError("redis unavailable")

    async def expire(self, *args, **kwargs):
        raise RuntimeError("redis unavailable")

    async def set(self, *args, **kwargs):
        raise RuntimeError("redis unavailable")

    async def delete(self, *args, **kwargs):
        raise RuntimeError("redis unavailable")


async def _make_user(db_session, *, permissions: list[str], password: str = "GoodPass123"):
    email = f"sec-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user_with_role(
        db_session,
        email=email,
        password=password,
        role_name=f"Sec {uuid.uuid4().hex[:6]}",
        permissions=permissions,
    )
    await db_session.commit()
    return user, email, password


@pytest.mark.asyncio
async def test_expired_password_forces_change(client, db_session):
    admin = await admin_headers(client)
    user, email, password = await _make_user(db_session, permissions=["pos.access"])

    # Age the password beyond the configured expiry.
    user.password_changed_at = utcnow() - timedelta(days=400)
    await db_session.commit()
    patched = await client.patch(
        "/api/v1/settings/app-config",
        json={"security": {"passwordExpiryDays": 180}},
        headers=admin,
    )
    assert patched.status_code == 200, patched.text

    data = await login(client, email, password)
    assert data["user"]["mustChangePassword"] is True
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # Every non-change endpoint is blocked with the dedicated 403 code.
    blocked = await client.get("/api/v1/pos/products/search", headers=headers)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    # The change flow itself is allowed and clears the flag.
    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": password, "new_password": "BrandNew123"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    again = await login(client, email, "BrandNew123")
    assert again["user"]["mustChangePassword"] is False
    ok = await client.get(
        "/api/v1/pos/products/search",
        headers={"Authorization": f"Bearer {again['access_token']}"},
    )
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_password_policy_rejects_weak_password(client):
    headers = await admin_headers(client)
    weak = await client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Weak Password",
            "email": f"weak-{uuid.uuid4().hex[:8]}@example.com",
            "password": "allletters",
            "role_id": (await client.get("/api/v1/admin/roles/options", headers=headers)).json()["data"][0]["id"],
        },
        headers=headers,
    )
    assert weak.status_code == 422, weak.text


@pytest.mark.asyncio
async def test_db_lockout_survives_redis_outage(client, db_session, monkeypatch):
    admin = await admin_headers(client)
    user, email, password = await _make_user(db_session, permissions=["pos.access"])

    await client.patch(
        "/api/v1/settings/app-config",
        json={"security": {"maxLoginAttempts": 2, "accountLockMinutes": 5}},
        headers=admin,
    )
    import app.modules.auth.service as auth_service

    monkeypatch.setattr(auth_service, "get_redis", lambda: _BrokenRedis())
    try:
        for _ in range(2):
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
            )
            assert response.status_code == 401, response.text
        locked = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert locked.status_code == 429, locked.text
    finally:
        await client.patch(
            "/api/v1/settings/app-config",
            json={"security": {"maxLoginAttempts": 5, "accountLockMinutes": 15}},
            headers=admin,
        )


@pytest.mark.asyncio
async def test_disabled_user_loses_access_immediately(client, db_session):
    admin = await admin_headers(client)
    user, email, password = await _make_user(db_session, permissions=["pos.access"])
    data = await login(client, email, password)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert (await client.get("/api/v1/pos/products/search", headers=headers)).status_code == 200

    disabled = await client.patch(
        f"/api/v1/admin/users/{user.id}", json={"status": "DISABLED"}, headers=admin
    )
    assert disabled.status_code == 200, disabled.text

    # The still-unexpired token is refused because the account is disabled.
    denied = await client.get("/api/v1/pos/products/search", headers=headers)
    assert denied.status_code in (401, 403), denied.text


@pytest.mark.asyncio
async def test_disabled_role_grants_no_permissions(client, db_session):
    user, email, password = await _make_user(db_session, permissions=["pos.access"])
    data = await login(client, email, password)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert (await client.get("/api/v1/pos/products/search", headers=headers)).status_code == 200

    # Disable the role directly (the API refuses while users reference it).
    from app.modules.auth.models import Role

    role = await db_session.get(Role, user.role_id)
    role.status = "DISABLED"
    await db_session.commit()

    denied = await client.get("/api/v1/pos/products/search", headers=headers)
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_role_change_invalidates_existing_tokens(client, db_session):
    admin = await admin_headers(client)
    user, email, password = await _make_user(db_session, permissions=["pos.access"])
    data = await login(client, email, password)
    old_headers = {"Authorization": f"Bearer {data['access_token']}"}

    # Move the user to a different role via the admin API.
    roles = (await client.get("/api/v1/admin/roles", headers=admin)).json()["data"]
    other = next(role for role in roles if role["name"] == "Administrator")
    changed = await client.patch(
        f"/api/v1/admin/users/{user.id}", json={"role_id": other["id"]}, headers=admin
    )
    assert changed.status_code == 200, changed.text

    # The token issued before the role change is now invalid (token_version bump).
    stale = await client.get("/api/v1/pos/products/search", headers=old_headers)
    assert stale.status_code == 401, stale.text
