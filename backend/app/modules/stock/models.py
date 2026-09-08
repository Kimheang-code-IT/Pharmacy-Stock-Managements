"""Product and stock balance models — spec section 4.2."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_name", "name"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_uom_id", "uom_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    # UOM is required (spec section 2.1.5); products always reference the live record.
    uom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=False
    )
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    expiry_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Pricing rows (spec 4.2 / §2.1.3 products): [{uom_id, uom_symbol,
    # convert_uom_id, convert_uom_symbol, factor_to_base, sale_price,
    # is_default_sale, cost_price?}]. Validated by the product service.
    uom_conversions: Mapped[list | None] = mapped_column(JSONB(astext_type=Text()), nullable=True, default=list)
    image_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    category_ref = relationship("Category", lazy="selectin")
    brand_ref = relationship("Brand", lazy="selectin")
    uom_ref = relationship("UOM", lazy="selectin")
    balance: Mapped["StockBalance | None"] = relationship(
        back_populates="product_ref", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    sale_prices: Mapped[list["ProductSalePrice"]] = relationship(
        back_populates="product_ref", lazy="selectin", cascade="all, delete-orphan"
    )


class StockBalance(Base):
    """Materialized current stock; updated only inside stock transactions."""

    __tablename__ = "stock_balances"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    average_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    product_ref: Mapped[Product] = relationship(back_populates="balance")


class ProductSalePrice(Base):
    """Versioned POS sale price (spec 4.2 product_sale_prices).

    Exactly one row per product is POS-active (partial unique index); the
    active row's sale_price is always copied onto products.selling_price in
    the same transaction, so POS and the Stock list can never diverge.
    Cost history is NOT stored here — it is derived from Stock In lots.
    """

    __tablename__ = "product_sale_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_product_sale_prices_product_version"),
        Index(
            "uq_product_sale_prices_one_active",
            "product_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_product_sale_prices_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    sale_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    product_ref: Mapped[Product] = relationship(back_populates="sale_prices")


class StockTransaction(Base):
    """Header for stock in / adjustment / damage / expire operations."""

    __tablename__ = "stock_transactions"
    __table_args__ = (Index("ix_stock_transactions_created_at", "transaction_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CONFIRMED")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["StockTransactionItem"]] = relationship(
        back_populates="transaction_ref", cascade="all, delete-orphan", lazy="selectin"
    )


class StockTransactionItem(Base):
    __tablename__ = "stock_transaction_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stock_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_transactions.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    system_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    actual_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    transaction_ref: Mapped[StockTransaction] = relationship(back_populates="items")
    product_ref: Mapped[Product] = relationship(lazy="selectin")


class StockMovement(Base):
    """Immutable, append-only record of every stock change."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_id", "product_id"),
        Index("ix_stock_movements_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product_ref: Mapped[Product] = relationship(lazy="selectin")
