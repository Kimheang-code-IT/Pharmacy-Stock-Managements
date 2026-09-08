from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, q, status, page, limit) -> tuple[list[Customer], int]:
        stmt = select(Customer)
        count_stmt = select(func.count()).select_from(Customer)
        if q:
            pattern = f"%{q.strip()}%"
            condition = Customer.name.ilike(pattern) | Customer.code.ilike(pattern) | Customer.phone.ilike(pattern)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(Customer.status == status)
            count_stmt = count_stmt.where(Customer.status == status)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Customer.name).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def get(self, customer_id) -> Customer | None:
        return await self.session.get(Customer, customer_id)

    async def get_by_code(self, code: str) -> Customer | None:
        result = await self.session.execute(select(Customer).where(Customer.code == code))
        return result.scalar_one_or_none()

    async def get_walk_in(self) -> Customer | None:
        result = await self.session.execute(
            select(Customer).where(Customer.is_walk_in.is_(True))
        )
        return result.scalar_one_or_none()

    def add(self, customer: Customer) -> None:
        self.session.add(customer)

    async def flush(self) -> None:
        await self.session.flush()
