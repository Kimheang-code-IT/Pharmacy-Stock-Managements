"""POS models: sales, sale items, returns, payments (spec section 4.2)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Resolves the string relation below for type checkers/linters; SQLAlchemy
    # resolves it through the declarative class registry at runtime.
    from app.modules.stock.models import BatchStockBalance


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        Index("ix_sales_sale_date", "sale_date"),
        Index("ix_sales_customer_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    sale_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Delivery fee included in grand_total (no second stock-out, spec 2.1.2).
    delivery_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    debt_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    # Document currency: every amount on this document is in THIS currency
    # (never mixed). exchange_rate = KHR per 1 USD (1 for USD documents).
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD", server_default="USD")
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False)
    sale_status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale_ref", cascade="all, delete-orphan", lazy="selectin"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    # Product link is nullable so a product can be hard-deleted while the sale
    # history survives through the name/sku/barcode snapshots.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Barcode snapshot (operational identifier); sku is legacy-optional.
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # UOM snapshot at transaction time (display on POS/invoice; spec section 2.1.3).
    uom_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    uom_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uom_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Stock is always mutated in the base UOM: base_qty = quantity × factor_to_base.
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sale_ref: Mapped[Sale] = relationship(back_populates="items")
    product_ref: Mapped["object"] = relationship("Product", lazy="selectin")
    batch_allocations: Mapped[list["SaleItemBatch"]] = relationship(
        back_populates="sale_item_ref", cascade="all, delete-orphan", lazy="selectin"
    )


class SaleItemBatch(Base):
    """Batch allocation behind one sold line (spec: sale_item_batches).

    Invariant: SUM(quantity_base) == sale_item.quantity × factor_to_base.
    One customer-visible sale line may draw from many FEFO batches; the
    cost_per_base snapshot lets reporting compute the blended cost without
    changing the customer price.
    """

    __tablename__ = "sale_item_batches"
    __table_args__ = (
        Index("ix_sale_item_batches_sale_item_id", "sale_item_id"),
        Index("ix_sale_item_batches_batch_id", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False
    )
    # Batch link is nullable so a product's batches can be removed on hard
    # delete while the sale line keeps its allocation snapshot.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_stock_balances.id", ondelete="SET NULL"), nullable=True
    )
    quantity_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Cost-per-BASE-unit snapshot (6dp to match batch_stock_balances.unit_cost).
    cost_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    # Sale-price snapshot for THIS allocation (spec: historical sales never
    # change when a batch price is edited later). NULL on rows written before
    # migration 0034 — readers fall back to the sale-item line figures.
    batch_no_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    conversion_qty_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    line_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sale_item_ref: Mapped[SaleItem] = relationship(back_populates="batch_allocations")
    batch_ref: Mapped["BatchStockBalance"] = relationship()


class SaleReturn(Base):
    __tablename__ = "sale_returns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    return_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["SaleReturnItem"]] = relationship(
        back_populates="return_ref", cascade="all, delete-orphan", lazy="selectin"
    )


class SaleReturnItem(Base):
    __tablename__ = "sale_return_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_return_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False
    )
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    restock: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    return_ref: Mapped[SaleReturn] = relationship(back_populates="items")


class Payment(Base):
    """Immutable payment records for sales and customer/supplier debt payments."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_customer_debt_id", "customer_debt_id"),
        Index("ix_payments_supplier_debt_id", "supplier_debt_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    customer_debt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_debts.id", ondelete="SET NULL"), nullable=True
    )
    supplier_debt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_debts.id", ondelete="SET NULL"), nullable=True
    )
    payment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
