from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.pos.models import Payment
from app.modules.suppliers.models import Supplier, SupplierDebt
from app.modules.suppliers.repository import SupplierRepository
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number

logger = logging.getLogger("stock_pos.suppliers")


class SupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplierRepository(session)

    async def list(self, *, q, status, page, limit) -> tuple[list[Supplier], int]:
        return await self.repo.list(q=q, status=status, page=page, limit=limit)

    async def get(self, supplier_id) -> Supplier:
        supplier = await self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        return supplier

    async def create(self, payload) -> Supplier:
        code = payload.code.strip() if payload.code else None
        if code:
            if await self.repo.get_by_code(code):
                raise ConflictError("A supplier with this code already exists")
        else:
            code = await allocate_document_number(self.session, "SUPPLIER")
        supplier = Supplier(
            code=code,
            name=payload.name.strip(),
            company_name=payload.company_name,
            phone=payload.phone,
            email=None,
            address=payload.location or payload.address,
            contact_person=payload.contact_person,
            note=payload.note,
            status=payload.status,
        )
        self.repo.add(supplier)
        await self.repo.flush()
        await self.session.commit()
        return supplier

    async def update(self, supplier_id, payload) -> Supplier:
        supplier = await self.get(supplier_id)
        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "location" in data:
            data["address"] = data.pop("location")
        data.pop("email", None)
        for key, value in data.items():
            setattr(supplier, key, value)
        await self.repo.flush()
        await self.session.commit()
        return supplier

    async def delete(self, supplier_id) -> None:
        supplier = await self.get(supplier_id)
        if await self.repo.count_debts(supplier.id) > 0:
            raise ConflictError("Cannot delete a supplier that has debt records")
        await self.session.delete(supplier)
        await self.session.commit()

    async def list_debts(self, supplier_id) -> list[tuple[SupplierDebt, object]]:
        """All debts of one supplier with the purchase (stock-in) date so every
        row shows Date + Document No (spec: Setup detail tables)."""
        from app.modules.stock.models import StockTransaction

        supplier = await self.get(supplier_id)
        result = await self.session.execute(
            select(SupplierDebt, StockTransaction.transaction_date)
            .join(StockTransaction, StockTransaction.id == SupplierDebt.stock_transaction_id)
            .where(SupplierDebt.supplier_id == supplier.id)
            .order_by(SupplierDebt.created_at.desc())
        )
        return [(debt, transaction_date) for debt, transaction_date in result.all()]

    async def pay_debt(self, supplier_id, debt_id, payload, *, actor: User) -> Payment:
        """Canonical supplier-debt payment: locks the debt row, rejects
        overpayment, and records an immutable payment transaction."""
        supplier = await self.get(supplier_id)
        result = await self.session.execute(
            select(SupplierDebt)
            .where(SupplierDebt.id == debt_id, SupplierDebt.supplier_id == supplier.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        debt = result.scalar_one_or_none()
        if debt is None:
            raise NotFoundError("Debt not found for this supplier")
        if debt.status == "PAID" or debt.remaining_amount <= 0:
            raise ConflictError("This debt is already settled")

        amount = Decimal(payload.amount).quantize(Decimal("0.01"))
        if amount > debt.remaining_amount:
            raise ValidationError(
                f"Payment exceeds the remaining debt ({debt.remaining_amount})",
                field_errors={"amount": "Overpayment rejected"},
            )

        payment = Payment(
            payment_no=await allocate_document_number(self.session, "SUPPLIER_DEBT_PAYMENT"),
            sale_id=None,
            supplier_id=supplier.id,
            supplier_debt_id=debt.id,
            payment_type="SUPPLIER_DEBT_PAYMENT",
            payment_method=payload.payment_method,
            amount=amount,
            reference_no=payload.reference_no,
            note=payload.note,
            created_by=actor.id,
        )
        self.session.add(payment)
        await self.session.flush()

        debt.paid_amount = debt.paid_amount + amount
        debt.remaining_amount = debt.remaining_amount - amount
        debt.status = "PAID" if debt.remaining_amount == 0 else "PARTIAL"

        await record_audit(
            self.session,
            action="supplier_debt_payment",
            module="suppliers",
            user_id=actor.id,
            entity_type="supplier_debt",
            entity_id=debt.id,
            new_values={
                "payment_no": payment.payment_no,
                "amount": str(amount),
                "remaining": str(debt.remaining_amount),
            },
        )
        await self.session.commit()
        return payment

    async def pay_open_debts(self, supplier_id, payload, *, actor: User) -> list[Payment]:
        """Supplier-level payment (no debt id chosen by the caller): settles
        open debts oldest-first in ONE transaction. Overpayment is rejected."""
        supplier = await self.get(supplier_id)
        result = await self.session.execute(
            select(SupplierDebt)
            .where(
                SupplierDebt.supplier_id == supplier.id,
                SupplierDebt.remaining_amount > 0,
            )
            .order_by(SupplierDebt.created_at.asc(), SupplierDebt.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        open_debts = list(result.scalars().all())
        total_outstanding = sum((debt.remaining_amount for debt in open_debts), Decimal("0.00"))

        amount = Decimal(payload.amount).quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValidationError("Payment must be greater than zero", field_errors={"amount": "Invalid amount"})
        if not open_debts or amount > total_outstanding:
            raise ValidationError(
                f"Payment exceeds the total outstanding debt ({total_outstanding})",
                field_errors={"amount": "Overpayment rejected"},
            )

        payments: list[Payment] = []
        to_apply = amount
        for debt in open_debts:
            if to_apply <= 0:
                break
            applied = min(to_apply, debt.remaining_amount)
            payment = Payment(
                payment_no=await allocate_document_number(self.session, "SUPPLIER_DEBT_PAYMENT"),
                sale_id=None,
                supplier_id=supplier.id,
                supplier_debt_id=debt.id,
                payment_type="SUPPLIER_DEBT_PAYMENT",
                payment_method=payload.payment_method,
                amount=applied,
                reference_no=payload.reference_no,
                note=payload.note,
                created_by=actor.id,
            )
            self.session.add(payment)
            await self.session.flush()

            debt.paid_amount = debt.paid_amount + applied
            debt.remaining_amount = debt.remaining_amount - applied
            debt.status = "PAID" if debt.remaining_amount == 0 else "PARTIAL"
            payments.append(payment)
            to_apply -= applied

        await record_audit(
            self.session,
            action="supplier_debt_payment",
            module="suppliers",
            user_id=actor.id,
            entity_type="supplier_debt",
            entity_id=payments[0].supplier_debt_id,
            new_values={
                "payments": [p.payment_no for p in payments],
                "amount": str(amount),
                "allocation": "oldest_first",
            },
        )
        await self.session.commit()
        return payments

    async def list_debt_payments(self, supplier_id, debt_id) -> list[Payment]:
        """Immutable payment history for one supplier debt."""
        supplier = await self.get(supplier_id)
        result = await self.session.execute(
            select(SupplierDebt)
            .where(SupplierDebt.id == debt_id, SupplierDebt.supplier_id == supplier.id)
        )
        debt = result.scalar_one_or_none()
        if debt is None:
            raise NotFoundError("Debt not found for this supplier")
        rows = await self.session.execute(
            select(Payment)
            .where(Payment.supplier_debt_id == debt.id)
            .order_by(Payment.created_at.asc())
        )
        return list(rows.scalars().all())

    async def list_payments(self, supplier_id) -> list[Payment]:
        """All debt payments of one supplier, newest first."""
        supplier = await self.get(supplier_id)
        rows = await self.session.execute(
            select(Payment)
            .where(Payment.supplier_id == supplier.id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
        )
        return list(rows.scalars().all())


async def create_supplier_debt_for_stock_in(
    session: AsyncSession,
    *,
    supplier_id,
    stock_transaction_id,
    document_no: str,
    original_amount,
    paid_amount,
) -> SupplierDebt:
    """Public interface: stock-in transactions create supplier debts in their own
    transaction when the purchase is not fully paid."""
    from decimal import Decimal

    from app.core.exceptions import NotFoundError
    from app.modules.suppliers.repository import SupplierRepository

    supplier = await SupplierRepository(session).get(supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found")

    original = Decimal(original_amount).quantize(Decimal("0.01"))
    paid = min(Decimal(paid_amount).quantize(Decimal("0.01")), original)
    remaining = original - paid
    debt = SupplierDebt(
        supplier_id=supplier.id,
        stock_transaction_id=stock_transaction_id,
        document_no=document_no,
        original_amount=original,
        paid_amount=paid,
        remaining_amount=remaining,
        status="UNPAID" if paid == 0 else "PARTIAL",
    )
    session.add(debt)
    await session.flush()
    return debt
