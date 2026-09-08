from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Permission, Role, RolePermission, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def any_user_exists(self) -> bool:
        result = await self.session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one()) > 0

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        user.email = user.email.lower()
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_last_login(self, user: User) -> None:
        from app.core.security import utcnow

        user.last_login_at = utcnow()
        await self.session.flush()

    async def bump_token_version(self, user: User) -> None:
        user.token_version = (user.token_version or 0) + 1
        await self.session.flush()


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, name: str) -> Role | None:
        result = await self.session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def create_system_role(self, name: str, description: str, permission_codes: list[str]) -> Role:
        role = Role(name=name, description=description, is_system=True, status="ACTIVE")
        self.session.add(role)
        await self.session.flush()
        await self.set_role_permissions(role, permission_codes)
        return role

    async def set_role_permissions(self, role: Role, permission_codes: list[str]) -> None:
        from sqlalchemy import delete

        await self.session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        if permission_codes:
            result = await self.session.execute(select(Permission).where(Permission.code.in_(permission_codes)))
            for permission in result.scalars().all():
                self.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await self.session.flush()
        # Re-sync the in-memory collection with the database without lazy IO.
        await self.session.refresh(role, attribute_names=["permission_rows"])

    async def sync_permission_catalog(self, catalog_codes: list[str]) -> None:
        """Insert missing permission catalog rows; never deletes existing ones."""
        result = await self.session.execute(select(Permission.code))
        existing = {row[0] for row in result.all()}
        from app.core.permissions import permission_catalog

        module_by_code = {
            permission: group["module"] for group in permission_catalog() for permission in group["permissions"]
        }
        for code in catalog_codes:
            if code in existing:
                continue
            if "." in code:
                module, action = code.rsplit(".", 1)
            else:
                module, action = "system", code.lower()
            self.session.add(
                Permission(code=code, module=module_by_code.get(code, module), action=action)
            )
        await self.session.flush()
