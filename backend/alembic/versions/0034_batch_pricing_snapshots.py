"""Batch pricing snapshots + manual batch active flag.

- sale_item_batches gains the per-allocation SALE PRICE snapshot (batch no,
  unit price, conversion qty, line amount) alongside the existing cost
  snapshot. Historical sales therefore never change when a batch price is
  edited later, and reports can show revenue/COGS per sold batch.
- batch_stock_balances gains a manual `is_active` flag so a lot can be pulled
  from POS without deleting its stock or its historical pricing (inactive lots
  are never allocated to a new sale; existing sales keep their snapshots).

Existing rows are backfilled safely: `is_active` defaults to true (all current
lots stay sellable) and the new snapshot columns are NULL for historic lines
(reporting falls back to the stored sale-item figures for those).

Revision ID: 0034_batch_pricing_snapshots
Revises: 0033_sale_price_uom_active
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_batch_pricing_snapshots"
down_revision = "0033_sale_price_uom_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Manual sellable flag on a physical lot (inactive = not offered on POS).
    op.add_column(
        "batch_stock_balances",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Batch-pricing lookup for POS FEFO eligibility.
    op.create_index(
        "ix_batch_stock_balances_product_active_expiry",
        "batch_stock_balances",
        ["product_id", "is_active", "expiry_date"],
    )

    # Per-allocation sale price snapshot (NULL for rows written before this
    # migration — readers fall back to the sale-item figures).
    op.add_column(
        "sale_item_batches",
        sa.Column("batch_no_snapshot", sa.String(100), nullable=True),
    )
    op.add_column(
        "sale_item_batches",
        sa.Column("unit_price_snapshot", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "sale_item_batches",
        sa.Column("conversion_qty_snapshot", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "sale_item_batches",
        sa.Column("line_amount", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_item_batches", "line_amount")
    op.drop_column("sale_item_batches", "conversion_qty_snapshot")
    op.drop_column("sale_item_batches", "unit_price_snapshot")
    op.drop_column("sale_item_batches", "batch_no_snapshot")
    op.drop_index("ix_batch_stock_balances_product_active_expiry", table_name="batch_stock_balances")
    op.drop_column("batch_stock_balances", "is_active")
