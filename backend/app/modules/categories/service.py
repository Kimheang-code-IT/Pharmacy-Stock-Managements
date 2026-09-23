from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository
from app.shared.audit.service import record_audit
from app.shared.lifecycle import assert_inactive_for_delete


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CategoryRepository(session)

    async def list(self, *, q, status, page, limit) -> tuple[list[Category], int]:
        return await self.repo.list(q=q, status=status, page=page, limit=limit)

    async def get(self, category_id: uuid.UUID) -> Category:
        category = await self.repo.get(category_id)
        if category is None:
            raise NotFoundError("Category not found")
        return category

    async def create(self, payload) -> Category:
        if await self.repo.get_by_code(payload.code.strip()):
            raise ConflictError("A category with this code already exists")
        category = Category(
            code=payload.code.strip(),
            name=payload.name.strip(),
            description=payload.description,
            status=payload.status,
        )
        self.repo.add(category)
        await self.repo.flush()
        await record_audit(
            self.session,
            action="category_created",
            module="categories",
            entity_type="category",
            entity_id=category.id,
            new_values={"code": category.code, "name": category.name, "status": category.status},
        )
        await self.session.commit()
        return category

    async def update(self, category_id: uuid.UUID, payload) -> Category:
        category = await self.get(category_id)
        old = {"code": category.code, "name": category.name, "status": category.status}
        if payload.code is not None:
            code = payload.code.strip()
            if code and code != category.code:
                if await self.repo.get_by_code(code):
                    raise ConflictError("A category with this code already exists")
                category.code = code
        if payload.name is not None:
            category.name = payload.name.strip()
        if payload.description is not None:
            category.description = payload.description
        if payload.status is not None:
            category.status = payload.status
        await self.repo.flush()
        await record_audit(
            self.session,
            action="category_updated",
            module="categories",
            entity_type="category",
            entity_id=category.id,
            old_values=old,
            new_values={"code": category.code, "name": category.name, "status": category.status},
        )
        await self.session.commit()
        return category

    async def delete(self, category_id: uuid.UUID) -> None:
        category = await self.get(category_id)
        assert_inactive_for_delete(category.status, label="category")
        if await self.repo.count_products(category_id) > 0:
            raise ConflictError(
                "Cannot delete this category because products reference it. "
                "Deactivate it instead."
            )
        snapshot = {"code": category.code, "name": category.name}
        await self.session.delete(category)
        await record_audit(
            self.session,
            action="category_deleted",
            module="categories",
            entity_type="category",
            entity_id=category.id,
            old_values=snapshot,
        )
        await self.session.commit()
