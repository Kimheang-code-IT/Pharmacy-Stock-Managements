"""product_sale_prices + products.uom_conversions + POS sale extras.

Revision ID: 0011_sale_prices_pos
Revises: 0010_expenses
Create Date: 2026-09-21

- product_sale_prices: versioned POS sale prices, at most one is_active per
  product (partial unique index). products.selling_price always mirrors the
  active version.
- products.uom_conversions: JSONB convert-UOM rows (spec 4.2 products).
- sales.delivery_price: delivery fee added into grand_total.
- sale_items.uom_id / factor_to_base / discount_percent: line UOM snapshot
  (stock is always mutated in the base UOM) and per-line percent discount.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_sale_prices_pos"
down_revision = "0010_expenses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_sale_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sale_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "version", name="uq_product_sale_prices_product_version"),
    )
    op.create_index(
        "ix_product_sale_prices_product_id",
        "product_sale_prices",
        ["product_id"],
    )
    # At most one POS-active version per product.
    op.create_index(
        "uq_product_sale_prices_one_active",
        "product_sale_prices",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.add_column("products", sa.Column("uom_conversions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column(
        "sales",
        sa.Column("delivery_price", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sale_items",
        sa.Column("uom_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sale_items",
        sa.Column("factor_to_base", sa.Numeric(18, 6), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "sale_items",
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "discount_percent")
    op.drop_column("sale_items", "factor_to_base")
    op.drop_column("sale_items", "uom_id")
    op.drop_column("sales", "delivery_price")
    op.drop_column("products", "uom_conversions")
    op.drop_index("uq_product_sale_prices_one_active", table_name="product_sale_prices")
    op.drop_index("ix_product_sale_prices_product_id", table_name="product_sale_prices")
    op.drop_table("product_sale_prices")
