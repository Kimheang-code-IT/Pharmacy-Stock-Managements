"""Telegram expiry alert state — spec section 3.6 (`telegram_expiry_alert_state`).

Tracks that an expiry alert level was already sent for a product lot so the
in-process API scheduler never spams. Uniqueness is enforced NULL-safely: batch_no
is nullable, so the unique index coalesces it to '' (plain unique constraints
treat NULLs as distinct in PostgreSQL and would not dedupe unbatched lots).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelegramExpiryAlertState(Base):
    __tablename__ = "telegram_expiry_alert_state"
    __table_args__ = (
        # Spec UNIQUE (product_id, batch_no, expiry_date, alert_level) with
        # NULL-safe batch handling for lots without a batch number.
        Index(
            "uq_telegram_expiry_alert_state_lot",
            "product_id",
            text("COALESCE(batch_no, '')"),
            "expiry_date",
            "alert_level",
            unique=True,
        ),
        UniqueConstraint(
            "product_id",
            "batch_no",
            "expiry_date",
            "alert_level",
            name="uq_telegram_expiry_alert_state_spec",
        ),
        Index("ix_telegram_expiry_alert_state_product_id", "product_id"),
    )

    ALERT_LEVEL_1 = 1
    ALERT_LEVEL_2 = 2

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    alert_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
