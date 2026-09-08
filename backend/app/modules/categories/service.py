from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository


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
        await self.session.commit()
        return category

    async def update(self, category_id: uuid.UUID, payload) -> Category:
        category = await self.get(category_id)
        if payload.code is not None and payload.code.strip() != category.code:
            if await self.repo.get_by_code(payload.code.strip()):
                raise ConflictError("A category with this code already exists")
            category.code = payload.code.strip()
        if payload.name is not None:
            category.name = payload.name.strip()
        if payload.description is not None:
            category.description = payload.description
        if payload.status is not None:
            category.status = payload.status
        await self.repo.flush()
        await self.session.commit()
        return category

    async def delete(self, category_id: uuid.UUID) -> None:
        category = await self.get(category_id)
        if await self.repo.count_products(category_id) > 0:
            raise ConflictError("Cannot delete a category that still has products")
        await self.session.delete(category)
        await self.session.commit()
