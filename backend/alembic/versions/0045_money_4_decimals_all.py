"""Widen all remaining money columns to 4 decimal places.

The app now accepts ``#,##0.####`` on every money input (products, pricing,
purchases, supplier/customer debts, expenses, stock valuation snapshots, POS
costs), so every money column left at ``numeric(18,2)`` is widened to
``numeric(18,4)``. Quantity columns are already ``numeric(18,4)``; the finer
cost columns (``batch_stock_balances.unit_cost``, ``sale_item_batches
.cost_per_base``) stay ``numeric(18,6)``.

Revision ID: 0045_money_4_decimals_all
Revises: 0044_pos_money_4_decimals
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0045_money_4_decimals_all"
down_revision = "0044_pos_money_4_decimals"
branch_labels = None
depends_on = None

# table -> money columns to widen (18,2 -> 18,4).
_COLUMNS: dict[str, tuple[str, ...]] = {
    "products": ("cost_price", "selling_price"),
    "stock_balances": ("average_cost",),
    "product_sale_prices": ("sale_price",),
    "product_sale_price_uoms": ("sale_price",),
    "stock_transactions": ("discount_amount", "tax_amount"),
    "purchase_returns": ("refund_amount", "debt_reduction", "credit_amount"),
    "purchase_return_items": ("unit_cost", "line_refund"),
    "stock_transaction_items": ("unit_cost", "line_total"),
    "stock_movements": ("unit_cost",),
    "supplier_debts": ("original_amount", "paid_amount", "remaining_amount"),
    "expenses": ("amount",),
    "sale_items": ("unit_cost",),
}


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(18, 2),
                type_=sa.Numeric(18, 4),
            )


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(18, 4),
                type_=sa.Numeric(18, 2),
            )
