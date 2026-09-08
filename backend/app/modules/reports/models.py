"""Finance models: operating expenses recorded on the Finance Report.

Income entries are NOT modelled here — they are derived read-only from
confirmed POS sales/payments so no money is duplicated outside POS
(spec section 2.1.10 Finance Report).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Expense(Base):
    """User-managed operating expense (Add Expense on Finance Report only).

    There is deliberately no frontend Expense page: this table backs the
    Finance Report table and summary cards only.
    """

    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_expenses_expense_date", "expense_date"),
        Index("ix_expenses_created_by", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional document reference shown in the Finance ledger Reference column
    # (falls back to the category when empty).
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
