"""Document sequence model — spec section 4.2 (document_sequences)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentSequence(Base):
    __tablename__ = "document_sequences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    next_number: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    number_length: Mapped[int] = mapped_column(nullable=False, default=6)
    reset_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
