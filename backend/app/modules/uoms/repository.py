from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stock.models import Product
from app.modules.uoms.models import UOM


class UOMRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q: str | None, status: str | None, page: int, limit: int) -> tuple[list[UOM], int]:
        stmt = select(UOM)
        count_stmt = select(func.count()).select_from(UOM)
        if q:
            pattern = f"%{q.strip()}%"
            condition = UOM.code.ilike(pattern) | UOM.name.ilike(pattern) | UOM.symbol.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(UOM.status == status)
            count_stmt = count_stmt.where(UOM.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(stmt.order_by(UOM.code).offset((page - 1) * limit).limit(limit))
        return list(rows.scalars().all()), int(total)

    async def get(self, uom_id: uuid.UUID) -> UOM | None:
        return await self.session.get(UOM, uom_id)

    async def get_by_code(self, code: str) -> UOM | None:
        result = await self.session.execute(select(UOM).where(UOM.code == code))
        return result.scalar_one_or_none()

    async def get_default(self) -> UOM | None:
        """PCS is the canonical default UOM used for backfills."""
        return await self.get_by_code("PCS")

    async def count_products(self, uom_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Product).where(Product.uom_id == uom_id)
        )
        return int(result.scalar_one())

    def add(self, uom: UOM) -> None:
        self.session.add(uom)

    async def flush(self) -> None:
        await self.session.flush()
