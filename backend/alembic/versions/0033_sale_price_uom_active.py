"""Per-UOM POS-active flag on sale-price version rows.

Each UOM price inside a sale-price version can be toggled Active / Inactive
for POS from the product Pricing tab. POS only charges UOMs whose row is
active; deactivating a row hides that sell UOM from the POS cart without
deleting the price version.

Revision ID: 0033_sale_price_uom_active
Revises: 0032_batch_identity_expiry
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0033_sale_price_uom_active"
down_revision = "0032_batch_identity_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_sale_price_uoms",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("product_sale_price_uoms", "is_active")
