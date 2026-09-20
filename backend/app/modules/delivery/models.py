"""Delivery Notes — fulfillment tracking of sold products (spec section 2.1.9).

Delivery Notes NEVER mutate stock: stock was already reduced when the POS sale
completed. They track delivery status only. One note may cover MANY invoices
of the SAME customer (delivery_note_sales); phone + location on the header are
the delivery-destination fields, plus driver/vehicle/fee/receiver fulfillment
metadata. Invoice delivery status is DERIVED from delivered quantities
(Not Delivered / Partially Delivered / Fully Delivered) — never stored.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DeliveryNote(Base):
    __tablename__ = "delivery_notes"
    __table_args__ = (
        Index("ix_delivery_notes_status", "status"),
        Index("ix_delivery_notes_customer_id", "customer_id"),
        Index("ix_delivery_notes_created_at", "created_at"),
    )

    STATUS_DRAFT = "PENDING"
    STATUS_CONFIRMED = "PREPARING"
    STATUS_OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "RETURNED"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    # NOT NULL (spec §2.1.9): the delivery destination is mandatory; the
    # service falls back to the customer snapshot when the caller omits it.
    delivery_phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    delivery_location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    driver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Currency of the note (USD|KHR): all linked invoices must share it, so
    # the note never mixes raw KHR and USD invoices.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Fulfillment header fields (spec §2.1.9 extended): scheduled/actual
    # delivery date, vehicle/plate, delivery fee and the receiver snapshot.
    delivery_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    received_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_DRAFT)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Linked invoices — many sales of the SAME customer on one note (spec §2.1.9).
    sales: Mapped[list["DeliveryNoteSale"]] = relationship(
        back_populates="delivery_note_ref", cascade="all, delete-orphan", lazy="selectin"
    )
    items: Mapped[list["DeliveryNoteItem"]] = relationship(
        back_populates="delivery_note_ref", cascade="all, delete-orphan", lazy="selectin"
    )


class DeliveryNoteSale(Base):
    __tablename__ = "delivery_note_sales"
    __table_args__ = (
        UniqueConstraint("delivery_note_id", "sale_id", name="uq_delivery_note_sales_note_sale"),
        Index("ix_delivery_note_sales_delivery_note_id", "delivery_note_id"),
        Index("ix_delivery_note_sales_sale_id", "sale_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_notes.id", ondelete="CASCADE"), nullable=False
    )
    sale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    # Invoice-no snapshot for list display / print without joins.
    invoice_no: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    delivery_note_ref: Mapped[DeliveryNote] = relationship(back_populates="sales")


class DeliveryNoteItem(Base):
    __tablename__ = "delivery_note_items"
    __table_args__ = (
        Index("ix_delivery_note_items_delivery_note_id", "delivery_note_id"),
        Index("ix_delivery_note_items_sale_item_id", "sale_item_id"),
        Index("ix_delivery_note_items_sale_id", "sale_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_notes.id", ondelete="CASCADE"), nullable=False
    )
    sale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False
    )
    # Product link is nullable so a product can be hard-deleted while the
    # delivery history survives through the product_name snapshot.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    uom_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    qty_ordered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_to_deliver: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_delivered: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    delivery_note_ref: Mapped[DeliveryNote] = relationship(back_populates="items")
