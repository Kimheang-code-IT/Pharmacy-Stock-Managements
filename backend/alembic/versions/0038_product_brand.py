"""Free-text product brand.

Adds `products.brand` — a user-entered manufacturer/brand name. The product
form's brand selector was removed, so the typed name is stored directly on the
product. Existing brand links are backfilled from the brands table so no data
is lost (brand_id is kept for legacy rows).

Revision ID: 0038_product_brand
Revises: 0037_ops_completeness
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_product_brand"
down_revision = "0037_ops_completeness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("brand", sa.String(200), nullable=True))
    # Preserve the brand currently linked via the master-data FK.
    op.execute(
        """
        UPDATE products
        SET brand = brands.name
        FROM brands
        WHERE products.brand_id = brands.id
          AND products.brand IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("products", "brand")
