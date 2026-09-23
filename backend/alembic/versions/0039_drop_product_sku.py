"""Remove the legacy product SKU.

Barcode is the single operational product identifier. Drops `products.sku`
(and its unique constraint) plus the `sku` snapshots on `sale_items` and
`stock_transaction_items`; the product name/barcode snapshots remain.

Revision ID: 0039_drop_product_sku
Revises: 0038_product_brand
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_drop_product_sku"
down_revision = "0038_product_brand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("sale_items", "sku")
    op.drop_column("stock_transaction_items", "sku")
    # Drops the column and its UNIQUE constraint together.
    op.drop_column("products", "sku")


def downgrade() -> None:
    op.add_column("products", sa.Column("sku", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_products_sku", "products", ["sku"])
    op.add_column("stock_transaction_items", sa.Column("sku", sa.String(100), nullable=True))
    op.add_column("sale_items", sa.Column("sku", sa.String(100), nullable=True))
