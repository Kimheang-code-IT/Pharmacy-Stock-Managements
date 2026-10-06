"""Widen POS sale/tender money columns to 4 decimal places.

The POS money inputs accept ``#,##0.####`` (thousand separators, up to four
decimals). Storing those values requires the sale-currency money columns to
carry four decimals; cost columns (``unit_cost``, ``cost_per_base``) stay at
their existing precision because they are canonical USD costs.

Only columns that hold SALE-currency user-facing amounts are widened:
sales, sale_items, sale_item_batches, sale_returns, sale_return_items,
payments, customer_debts and delivery_notes.

Revision ID: 0044_pos_money_4_decimals
Revises: 0043_six_digit_product_barcodes
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_pos_money_4_decimals"
down_revision = "0043_six_digit_product_barcodes"
branch_labels = None
depends_on = None

# table -> sale-currency money columns to widen (18,2 -> 18,4).
_COLUMNS: dict[str, tuple[str, ...]] = {
    "sales": (
        "subtotal",
        "discount_amount",
        "grand_total",
        "delivery_price",
        "paid_amount",
        "debt_amount",
    ),
    "sale_items": (
        "unit_price",
        "discount_amount",
        "line_total",
    ),
    "sale_item_batches": (
        "unit_price_snapshot",
        "line_amount",
    ),
    "sale_returns": (
        "refund_amount",
        "refund_paid_amount",
        "credit_amount",
        "debt_reduction",
    ),
    "sale_return_items": ("refund_amount",),
    "payments": ("amount",),
    "customer_debts": (
        "original_amount",
        "paid_amount",
        "remaining_amount",
    ),
    "delivery_notes": ("delivery_fee",),
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
