from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category
from app.modules.stock.models import Product


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q: str | None, status: str | None, page: int, limit: int) -> tuple[list[Category], int]:
        stmt = select(Category)
        count_stmt = select(func.count()).select_from(Category)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Category.code.ilike(pattern) | Category.name.ilike(pattern))
            count_stmt = count_stmt.where(Category.code.ilike(pattern) | Category.name.ilike(pattern))
        if status:
            stmt = stmt.where(Category.status == status)
            count_stmt = count_stmt.where(Category.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Category.name).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, category_id: uuid.UUID) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_by_code(self, code: str) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.code == code))
        return result.scalar_one_or_none()

    async def count_products(self, category_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Product).where(Product.category_id == category_id)
        )
        return int(result.scalar_one())

    def add(self, category: Category) -> None:
        self.session.add(category)

    async def flush(self) -> None:
        await self.session.flush()
