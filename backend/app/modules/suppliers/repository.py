from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.suppliers.models import Supplier, SupplierDebt


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

    async def debt_balances(self, supplier_ids: list[UUID]) -> dict[UUID, dict[str, Decimal]]:
        """Open (remaining > 0) debt totals per supplier **and document currency**
        — the Suppliers list 'Outstanding Debt' column. Live sums over the debt
        rows, so every payment is reflected immediately and amounts of different
        currencies are never added together."""
        if not supplier_ids:
            return {}
        result = await self.session.execute(
            select(
                SupplierDebt.supplier_id,
                SupplierDebt.currency,
                func.coalesce(func.sum(SupplierDebt.remaining_amount), 0),
            )
            .where(SupplierDebt.supplier_id.in_(supplier_ids), SupplierDebt.remaining_amount > 0)
            .group_by(SupplierDebt.supplier_id, SupplierDebt.currency)
        )
        balances: dict[UUID, dict[str, Decimal]] = {}
        for supplier_id, currency, total in result.all():
            balances.setdefault(supplier_id, {})[str(currency or "USD")] = total
        return balances

    async def get(self, supplier_id) -> Supplier | None:
        return await self.session.get(Supplier, supplier_id)

    async def get_by_code(self, code: str) -> Supplier | None:
        result = await self.session.execute(select(Supplier).where(Supplier.code == code))
        return result.scalar_one_or_none()

    def add(self, supplier: Supplier) -> None:
        self.session.add(supplier)

    async def count_debts(self, supplier_id) -> int:
        from app.modules.suppliers.models import SupplierDebt

        result = await self.session.execute(
            select(func.count()).select_from(SupplierDebt).where(SupplierDebt.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def count_purchases(self, supplier_id) -> int:
        """Stock-in (purchase) documents recorded against the supplier."""
        from app.modules.stock.models import StockTransaction

        result = await self.session.execute(
            select(func.count())
            .select_from(StockTransaction)
            .where(StockTransaction.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def count_purchase_returns(self, supplier_id) -> int:
        from app.modules.stock.models import PurchaseReturn

        result = await self.session.execute(
            select(func.count())
            .select_from(PurchaseReturn)
            .where(PurchaseReturn.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def count_payments(self, supplier_id) -> int:
        from app.modules.pos.models import Payment

        result = await self.session.execute(
            select(func.count()).select_from(Payment).where(Payment.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def count_batches(self, supplier_id) -> int:
        from app.modules.stock.models import BatchStockBalance

        result = await self.session.execute(
            select(func.count())
            .select_from(BatchStockBalance)
            .where(BatchStockBalance.supplier_id == supplier_id)
        )
        return int(result.scalar_one())

    async def flush(self) -> None:
        await self.session.flush()
