from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.models import SystemSetting
from app.modules.auth.models import Role, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q: str | None, status: str | None, page: int, limit: int) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(User.full_name.ilike(pattern) | User.email.ilike(pattern))
            count_stmt = count_stmt.where(User.full_name.ilike(pattern) | User.email.ilike(pattern))
        if status:
            stmt = stmt.where(User.status == status)
            count_stmt = count_stmt.where(User.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def count_administrators_excluding(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .join(Role, User.role_id == Role.id)
            .where(Role.name == "Administrator", User.status == "ACTIVE", User.id != user_id)
        )
        return int(result.scalar_one())


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Role]:
        result = await self.session.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    async def get(self, role_id: UUID) -> Role | None:
        result = await self.session.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Role | None:
        result = await self.session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def create(self, name: str, description: str | None, permission_codes: list[str]) -> Role:
        from app.modules.auth.repository import RoleRepository as AuthRoleRepository

        delegate = AuthRoleRepository(self.session)
        role = await delegate.create_system_role(name, description or "", permission_codes)
        role.is_system = False
        return role

    async def set_permissions(self, role: Role, permission_codes: list[str]) -> None:
        from app.modules.auth.repository import RoleRepository as AuthRoleRepository

        await AuthRoleRepository(self.session).set_role_permissions(role, permission_codes)

    async def count_users_with_role(self, role_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.role_id == role_id)
        )
        return int(result.scalar_one())


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[SystemSetting]:
        result = await self.session.execute(select(SystemSetting).order_by(SystemSetting.key))
        return list(result.scalars().all())

    async def upsert(
        self, group_name: str, key: str, value: object, *, is_secret: bool, updated_by: UUID | None
    ) -> SystemSetting:
        result = await self.session.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = SystemSetting(
                group_name=group_name, key=key, value={"v": value}, is_secret=is_secret, updated_by=updated_by
            )
            self.session.add(setting)
        else:
            setting.value = {"v": value}
            setting.is_secret = is_secret
            setting.updated_by = updated_by
            setting.group_name = group_name
        await self.session.flush()
        return setting
