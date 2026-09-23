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
    # Document currency: every amount on this document is in THIS currency
    # (never mixed). exchange_rate = KHR per 1 USD (1 for USD documents).
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD", server_default="USD")
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Lifecycle: DRAFT | POSTED | VOID. Only POSTED expenses affect reports and
    # cash flow. Posted rows are immutable; corrections use VOID + replacement.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="POSTED", server_default="POSTED"
    )
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attachment_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
