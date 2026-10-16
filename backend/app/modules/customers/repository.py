from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer, CustomerDebt


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

    async def debt_balances(self, customer_ids: list[UUID]) -> dict[UUID, dict[str, Decimal]]:
        """Open (remaining > 0) debt totals per customer **and document currency**
        — the Customers list 'Outstanding Debt' column. Live sums over the debt
        rows, so every payment is reflected immediately and amounts of different
        currencies are never added together."""
        if not customer_ids:
            return {}
        result = await self.session.execute(
            select(
                CustomerDebt.customer_id,
                CustomerDebt.currency,
                func.coalesce(func.sum(CustomerDebt.remaining_amount), 0),
            )
            .where(CustomerDebt.customer_id.in_(customer_ids), CustomerDebt.remaining_amount > 0)
            .group_by(CustomerDebt.customer_id, CustomerDebt.currency)
        )
        balances: dict[UUID, dict[str, Decimal]] = {}
        for customer_id, currency, total in result.all():
            balances.setdefault(customer_id, {})[str(currency or "USD")] = total
        return balances

    async def get(self, customer_id) -> Customer | None:
        return await self.session.get(Customer, customer_id)

    async def get_by_code(self, code: str) -> Customer | None:
        result = await self.session.execute(select(Customer).where(Customer.code == code))
        return result.scalar_one_or_none()

    def add(self, customer: Customer) -> None:
        self.session.add(customer)

    async def count_sales(self, customer_id) -> int:
        from app.modules.pos.models import Sale

        result = await self.session.execute(
            select(func.count()).select_from(Sale).where(Sale.customer_id == customer_id)
        )
        return int(result.scalar_one())

    async def count_debts(self, customer_id) -> int:
        from app.modules.customers.models import CustomerDebt

        result = await self.session.execute(
            select(func.count())
            .select_from(CustomerDebt)
            .where(CustomerDebt.customer_id == customer_id)
        )
        return int(result.scalar_one())

    async def count_delivery_notes(self, customer_id) -> int:
        from app.modules.delivery.models import DeliveryNote

        result = await self.session.execute(
            select(func.count())
            .select_from(DeliveryNote)
            .where(DeliveryNote.customer_id == customer_id)
        )
        return int(result.scalar_one())

    async def count_payments(self, customer_id) -> int:
        from app.modules.pos.models import Payment

        result = await self.session.execute(
            select(func.count()).select_from(Payment).where(Payment.customer_id == customer_id)
        )
        return int(result.scalar_one())

    async def flush(self) -> None:
        await self.session.flush()
