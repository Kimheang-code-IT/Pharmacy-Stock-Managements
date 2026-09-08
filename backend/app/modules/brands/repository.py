from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brands.models import Brand
from app.modules.stock.models import Product


class BrandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q: str | None, status: str | None, page: int, limit: int) -> tuple[list[Brand], int]:
        stmt = select(Brand)
        count_stmt = select(func.count()).select_from(Brand)
        if q:
            pattern = f"%{q.strip()}%"
            condition = Brand.code.ilike(pattern) | Brand.name.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(Brand.status == status)
            count_stmt = count_stmt.where(Brand.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Brand.name).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, brand_id: uuid.UUID) -> Brand | None:
        return await self.session.get(Brand, brand_id)

    async def get_by_code(self, code: str) -> Brand | None:
        result = await self.session.execute(select(Brand).where(Brand.code == code))
        return result.scalar_one_or_none()

    async def count_products(self, brand_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Product).where(Product.brand_id == brand_id)
        )
        return int(result.scalar_one())

    def add(self, brand: Brand) -> None:
        self.session.add(brand)

    async def flush(self) -> None:
        await self.session.flush()
