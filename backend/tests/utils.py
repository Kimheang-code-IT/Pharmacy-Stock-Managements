"""Shared async test helpers."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.auth.models import Role, User
from tests.conftest import DEFAULT_UOM_ID

__all__ = ["DEFAULT_UOM_ID", "login", "admin_headers", "create_user_with_role"]


async def login(client, email: str, password: str) -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def admin_headers(client) -> dict:
    data = await login(client, "admin@gmail.com", "123456")
    return {"Authorization": f"Bearer {data['access_token']}"}


async def uom_option(client, headers, code: str = "PCS") -> dict:
    """Fetch an active UOM option (seeded defaults, spec section 2.1.3)."""
    response = await client.get("/api/v1/uoms/options", headers=headers)
    assert response.status_code == 200, response.text
    for row in response.json()["data"]:
        if row["code"] == code:
            return row
    raise AssertionError(f"UOM {code} is not seeded")


async def create_user_with_role(
    session: AsyncSession, *, email: str, password: str, role_name: str, permissions: list[str]
) -> User:
    role = Role(name=role_name, is_system=False, status="ACTIVE")
    session.add(role)
    await session.flush()
    from app.core.permissions import normalize_role_permissions

    codes = normalize_role_permissions(permissions, allow_wildcard=False)
    from sqlalchemy import select

    from app.modules.auth.models import Permission, RolePermission

    rows = await session.execute(select(Permission).where(Permission.code.in_(codes)))
    for permission in rows.scalars().all():
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    user = User(
        full_name=f"User {email}",
        email=email,
        password_hash=hash_password(password),
        role_id=role.id,
        status="ACTIVE",
    )
    session.add(user)
    await session.flush()
    return user
