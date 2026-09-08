"""brands master data + products.brand_id link

Revision ID: 0006_brands
Revises: 0005_payment_debt_links
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_brands"
down_revision = "0005_payment_debt_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_object_key", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_brands_code", "brands", ["code"])

    op.add_column(
        "products",
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_products_brand_id", "products", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_column("products", "brand_id")
    op.drop_constraint("uq_brands_code", "brands", type_="unique")
    op.drop_table("brands")
