from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.suppliers.models import Supplier


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q, status, page, limit) -> tuple[list[Supplier], int]:
        stmt = select(Supplier)
        count_stmt = select(func.count()).select_from(Supplier)
        if q:
            pattern = f"%{q.strip()}%"
            condition = Supplier.name.ilike(pattern) | Supplier.code.ilike(pattern) | Supplier.phone.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(Supplier.status == status)
            count_stmt = count_stmt.where(Supplier.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Supplier.name).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, supplier_id) -> Supplier | None:
        return await self.session.get(Supplier, supplier_id)

    async def get_by_code(self, code: str) -> Supplier | None:
        result = await self.session.execute(select(Supplier).where(Supplier.code == code))
        return result.scalar_one_or_none()

    def add(self, supplier: Supplier) -> None:
        self.session.add(supplier)

    async def count_debts(self, supplier_id) -> int:
        from sqlalchemy import select as _select

        from app.modules.suppliers.models import SupplierDebt

        result = await self.session.execute(
            _select(func.count()).select_from(SupplierDebt).where(SupplierDebt.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def flush(self) -> None:
        await self.session.flush()
