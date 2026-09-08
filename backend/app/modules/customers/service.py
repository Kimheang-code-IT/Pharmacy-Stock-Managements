from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.customers.repository import CustomerRepository
from app.modules.pos.models import Payment
from app.shared.audit.service import record_audit
from app.shared.documents import allocate_document_number

logger = logging.getLogger("stock_pos.customers")


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CustomerRepository(session)

    async def list(self, *, q, status, page, limit) -> tuple[list[Customer], int]:
        return await self.repo.list(q=q, status=status, page=page, limit=limit)

    async def get(self, customer_id) -> Customer:
        customer = await self.repo.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def create(self, payload) -> Customer:
        code = payload.code.strip() if payload.code else None
        if code:
            if await self.repo.get_by_code(code):
                raise ConflictError("A customer with this code already exists")
        else:
            code = await allocate_document_number(self.session, "CUSTOMER")
        customer = Customer(
            code=code,
            name=payload.name.strip(),
            phone=payload.phone,
            email=None,
            address=payload.location or payload.address,
            note=payload.note,
            status=payload.status,
            is_walk_in=False,
        )
        self.repo.add(customer)
        await self.repo.flush()
        await self.session.commit()
        return customer

    async def update(self, customer_id, payload) -> Customer:
        customer = await self.get(customer_id)
        if customer.is_walk_in:
            raise ConflictError("The walk-in customer is a system record and cannot be edited")
        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "location" in data:
            data["address"] = data.pop("location")
        data.pop("email", None)
        for key, value in data.items():
            setattr(customer, key, value)
        await self.repo.flush()
        await self.session.commit()
        return customer

    async def delete(self, customer_id) -> None:
        customer = await self.get(customer_id)
        if customer.is_walk_in:
            raise ConflictError("The walk-in customer cannot be deleted")
        await self.session.delete(customer)
        await self.session.commit()

    # ------------------------------------------------------------- debts

    async def list_debts(self, customer_id) -> list[tuple[CustomerDebt, object]]:
        """Open/all debts of one customer with the invoice (sale) date so every
        row shows Date + Invoice No (spec: Setup detail tables)."""
        from app.modules.pos.models import Sale

        customer = await self.get(customer_id)
        result = await self.session.execute(
            select(CustomerDebt, Sale.sale_date)
            .join(Sale, Sale.id == CustomerDebt.sale_id)
            .where(CustomerDebt.customer_id == customer.id)
            # Oldest first so the list agrees with pay_open_debts (oldest settled first).
            .order_by(CustomerDebt.created_at.asc(), CustomerDebt.id.asc())
        )
        return [(debt, sale_date) for debt, sale_date in result.all()]

    async def purchase_history(self, customer_id, *, page: int, limit: int):
        from app.modules.pos.models import Sale

        customer = await self.get(customer_id)
        count_stmt = (
            select(func.count()).select_from(Sale).where(Sale.customer_id == customer.id)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            select(Sale)
            .where(Sale.customer_id == customer.id)
            .order_by(Sale.sale_date.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [
            {
                "id": str(sale.id),
                "invoice_no": sale.invoice_no,
                "sale_date": sale.sale_date.isoformat(),
                "grand_total": str(sale.grand_total),
                "paid_amount": str(sale.paid_amount),
                "debt_amount": str(sale.debt_amount),
                "payment_status": sale.payment_status,
                "sale_status": sale.sale_status,
            }
            for sale in rows.scalars().all()
        ], int(total)

    async def pay_debt(self, customer_id, debt_id, payload, *, actor: User) -> Payment:
        """Canonical customer-debt payment: locks the debt row, rejects
        overpayment, and records an immutable payment transaction."""
        customer = await self.get(customer_id)
        result = await self.session.execute(
            select(CustomerDebt)
            .where(CustomerDebt.id == debt_id, CustomerDebt.customer_id == customer.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        debt = result.scalar_one_or_none()
        if debt is None:
            raise NotFoundError("Debt not found for this customer")
        if debt.status == "PAID" or debt.remaining_amount <= 0:
            raise ConflictError("This debt is already settled")

        amount = Decimal(payload.amount).quantize(Decimal("0.01"))
        if amount > debt.remaining_amount:
            raise ValidationError(
                f"Payment exceeds the remaining debt ({debt.remaining_amount})",
                field_errors={"amount": "Overpayment rejected"},
            )

        payment = Payment(
            payment_no=await allocate_document_number(self.session, "CUSTOMER_DEBT_PAYMENT"),
            sale_id=debt.sale_id,
            customer_id=customer.id,
            customer_debt_id=debt.id,
            payment_type="CUSTOMER_DEBT_PAYMENT",
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
            action="customer_debt_payment",
            module="customers",
            user_id=actor.id,
            entity_type="customer_debt",
            entity_id=debt.id,
            new_values={
                "payment_no": payment.payment_no,
                "amount": str(amount),
                "remaining": str(debt.remaining_amount),
            },
        )
        await self.session.commit()
        await self._queue_payment_notify(payment, debt=debt, customer=customer, amount=amount, actor=actor)
        return payment

    async def pay_open_debts(self, customer_id, payload, *, actor: User) -> list[Payment]:
        """Customer-level payment (no debt id chosen by the caller): settles
        open debts oldest-first in ONE transaction. Overpayment is rejected —
        there is no customer credit account."""
        customer = await self.get(customer_id)
        result = await self.session.execute(
            select(CustomerDebt)
            .where(
                CustomerDebt.customer_id == customer.id,
                CustomerDebt.remaining_amount > 0,
            )
            .order_by(CustomerDebt.created_at.asc(), CustomerDebt.id.asc())
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
                payment_no=await allocate_document_number(self.session, "CUSTOMER_DEBT_PAYMENT"),
                sale_id=debt.sale_id,
                customer_id=customer.id,
                customer_debt_id=debt.id,
                payment_type="CUSTOMER_DEBT_PAYMENT",
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
            action="customer_debt_payment",
            module="customers",
            user_id=actor.id,
            entity_type="customer_debt",
            entity_id=payments[0].customer_debt_id,
            new_values={
                "payments": [p.payment_no for p in payments],
                "amount": str(amount),
                "allocation": "oldest_first",
            },
        )
        await self.session.commit()
        for payment in payments:
            debt = next(d for d in open_debts if d.id == payment.customer_debt_id)
            self._queue_payment_notify_safe(payment, debt=debt, customer=customer, amount=payment.amount, actor=actor)
        return payments

    def _queue_payment_notify_safe(self, payment, **kwargs) -> None:
        try:
            self._queue_payment_notify(payment, **kwargs)
        except Exception:
            logger.exception("Telegram payment notify hook failed")

    async def _queue_payment_notify(self, payment, *, debt, customer, amount, actor) -> None:
        """Best-effort Telegram invoice text after a committed debt payment
        (spec 3.6.2). Never raises after the transaction has committed."""
        try:
            from app.modules.administration import get_setting_value

            enabled = await get_setting_value(
                self.session,
                "telegram",
                "payment_invoice_notify_enabled",
                True,
            )
            if not enabled:
                return
            from datetime import datetime, timezone

            from app.shared.telegram import queue_payment_invoice_notify

            queue_payment_invoice_notify(
                {
                    "kind": "DEBT_PAYMENT",
                    "invoice_no": debt.invoice_no,
                    "payment_no": payment.payment_no,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "customer": customer.name,
                    "total": str(debt.original_amount),
                    "paid": str(amount),
                    "payment_method": payment.payment_method,
                    "remaining": str(debt.remaining_amount),
                    "cashier": actor.full_name,
                }
            )
        except Exception:
            import logging

            logging.getLogger("stock_pos.customers").warning(
                "Telegram payment notify hook failed for %s", debt.invoice_no, exc_info=True
            )

    async def list_debt_payments(self, customer_id, debt_id) -> list[Payment]:
        """Immutable payment history for one customer debt (deposit + payments)."""
        customer = await self.get(customer_id)
        result = await self.session.execute(
            select(CustomerDebt)
            .where(CustomerDebt.id == debt_id, CustomerDebt.customer_id == customer.id)
        )
        debt = result.scalar_one_or_none()
        if debt is None:
            raise NotFoundError("Debt not found for this customer")
        rows = await self.session.execute(
            select(Payment)
            .where(Payment.customer_debt_id == debt.id)
            .order_by(Payment.created_at.asc())
        )
        return list(rows.scalars().all())

    async def list_payments(self, customer_id) -> list[Payment]:
        """All debt payments of one customer, newest first."""
        customer = await self.get(customer_id)
        rows = await self.session.execute(
            select(Payment)
            .where(Payment.customer_id == customer.id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
        )
        return list(rows.scalars().all())

