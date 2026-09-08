import pytest

from tests.utils import admin_headers, create_user_with_role, login

STAFF_EMAIL = "staff@example.com"
STAFF_PASSWORD = "staffpass1"


@pytest.fixture
async def staff_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=STAFF_EMAIL,
        password=STAFF_PASSWORD,
        role_name="CounterStaff",
        permissions=["category.view", "customer.view"],
    )
    await db_session.commit()
    data = await login(client, STAFF_EMAIL, STAFF_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def test_admin_requires_user_manage_permission(client, staff_headers):
    for method, path in (("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/roles"), ("get", "/api/v1/admin/audit-logs"), ("get", "/api/v1/admin/settings"), ("get", "/api/v1/admin/document-sequences")):
        response = await getattr(client, method)(path, headers=staff_headers)
        assert response.status_code == 403, f"{path} must deny user.manage-less users"

    response = await client.get("/api/v1/categories", headers=staff_headers)
    assert response.status_code == 200
    response = await client.post(
        "/api/v1/categories", json={"code": "NOPE", "name": "Nope"}, headers=staff_headers
    )
    assert response.status_code == 403


async def test_users_crud_and_password_reset(client):
    headers = await admin_headers(client)

    roles = await client.get("/api/v1/admin/roles", headers=headers)
    assert roles.status_code == 200
    admin_role_id = next(r["id"] for r in roles.json()["data"] if r["name"] == "Administrator")

    created = await client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Manageable User",
            "email": "manageable@example.com",
            "password": "userpass123",
            "role_id": admin_role_id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user = created.json()["data"]
    user_id = user["id"]

    patched = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"full_name": "Renamed User", "telegram_chat_id": "555444333"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["full_name"] == "Renamed User"

    # Duplicate email rejected
    dup = await client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Dup",
            "email": "manageable@example.com",
            "password": "userpass123",
            "role_id": admin_role_id,
        },
        headers=headers,
    )
    assert dup.status_code == 409

    # Reset password, then log in with it
    reset = await client.post(
        f"/api/v1/admin/users/{user_id}/reset-password",
        json={"new_password": "freshpass123"},
        headers=headers,
    )
    assert reset.status_code == 200
    login = await client.post(
        "/api/v1/auth/login", json={"email": "manageable@example.com", "password": "freshpass123"}
    )
    assert login.status_code == 200

    # Cannot disable the last active administrator (the seeded admin)
    me = await client.get("/api/v1/auth/me", headers=headers)
    admin_id = me.json()["data"]["id"]
    disable_self = await client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"status": "DISABLED"}, headers=headers
    )
    assert disable_self.status_code == 422


async def test_roles_crud_and_permission_catalog(client):
    headers = await admin_headers(client)

    catalog = await client.get("/api/v1/admin/permissions", headers=headers)
    assert catalog.status_code == 200
    modules = {entry["module"] for entry in catalog.json()["data"]}
    assert {"dashboard", "category", "stock", "supplier", "pos", "customer", "report", "user", "role", "sequence", "audit", "settings"} <= modules

    created = await client.post(
        "/api/v1/admin/roles",
        json={"name": "Auditor", "description": "Read-only", "permissions": ["audit.view", "report.sales"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    role = created.json()["data"]
    assert set(role["permissions"]) == {"audit.view", "report.sales"}

    updated = await client.patch(
        f"/api/v1/admin/roles/{role['id']}",
        json={"permissions": ["audit.view", "category.view"]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert set(updated.json()["data"]["permissions"]) == {"audit.view", "category.view"}

    unknown = await client.patch(
        f"/api/v1/admin/roles/{role['id']}",
        json={"permissions": ["not.a.permission"]},
        headers=headers,
    )
    assert unknown.status_code == 422

    dup = await client.post(
        "/api/v1/admin/roles", json={"name": "Auditor", "permissions": []}, headers=headers
    )
    assert dup.status_code == 409


async def test_document_sequences_list_and_patch(client):
    headers = await admin_headers(client)
    listing = await client.get("/api/v1/admin/document-sequences", headers=headers)
    assert listing.status_code == 200
    data = listing.json()["data"]
    types = {row["document_type"] for row in data}
    assert {"INVOICE", "STOCK_IN", "CUSTOMER", "SUPPLIER"} <= types

    invoice = next(row for row in data if row["document_type"] == "INVOICE")
    patched = await client.patch(
        f"/api/v1/admin/document-sequences/{invoice['id']}",
        json={"prefix": "RCPT", "number_length": 8},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["prefix"] == "RCPT"
    assert patched.json()["data"]["number_length"] == 8


async def test_settings_get_patch_and_masking(client):
    headers = await admin_headers(client)
    current = await client.get("/api/v1/admin/settings", headers=headers)
    assert current.status_code == 200
    groups = current.json()["data"]["groups"]
    assert "shop" in groups and "pos" in groups

    patched = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"shop": {"shop_name": "Khmer Mart"}, "pos": {"allow_negative_stock": True}}},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["groups"]["shop"]["shop_name"] == "Khmer Mart"
    assert patched.json()["data"]["groups"]["pos"]["allow_negative_stock"] is True

    # Restore defaults so later suites start from a neutral state.
    restored = await client.patch(
        "/api/v1/admin/settings",
        json={"values": {"shop": {"shop_name": "My Shop"}, "pos": {"allow_negative_stock": False}}},
        headers=headers,
    )
    assert restored.status_code == 200

    unknown = await client.patch(
        "/api/v1/admin/settings", json={"values": {"bogus": {"key": 1}}}, headers=headers
    )
    assert unknown.status_code == 422


async def test_audit_logs_listing(client):
    headers = await admin_headers(client)
    listing = await client.get("/api/v1/admin/audit-logs", headers=headers)
    assert listing.status_code == 200
    data = listing.json()["data"]
    actions = {row["action"] for row in data}
    assert "login" in actions
    meta = listing.json()["meta"]
    assert meta["total"] >= len(data)
