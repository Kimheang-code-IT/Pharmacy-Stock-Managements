"""UOM model — spec section 2.1.3 (units of measure)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UOM(Base):
    __tablename__ = "units_of_measure"
    __table_args__ = (UniqueConstraint("code", name="uq_units_of_measure_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# Development seed examples (spec section 2.1.3).
DEFAULT_UOMS: tuple[tuple[str, str, str], ...] = (
    ("PCS", "Piece", "pcs"),
    ("BOX", "Box", "box"),
    ("CAN", "Can", "can"),
    ("BTL", "Bottle", "btl"),
    ("KG", "Kilogram", "kg"),
    ("PACK", "Pack", "pack"),
)
