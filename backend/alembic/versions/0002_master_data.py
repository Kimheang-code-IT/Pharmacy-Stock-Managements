"""master data: sequences, settings, categories, products, balances, suppliers, customers

Revision ID: 0002_master_data
Revises: 0001_auth_audit
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_master_data"
down_revision = "0001_auth_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_type", sa.String(50), nullable=False, unique=True),
        sa.Column("prefix", sa.String(20), nullable=False),
        sa.Column("next_number", sa.BigInteger(), nullable=False),
        sa.Column("number_length", sa.Integer(), nullable=False),
        sa.Column("reset_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "system_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_name", sa.String(50), nullable=False),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sku", sa.String(100), nullable=False, unique=True),
        sa.Column("barcode", sa.String(100), nullable=True, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cost_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("selling_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("minimum_stock", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("expiry_tracking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image_object_key", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category_id", "products", ["category_id"])

    op.create_table(
        "stock_balances",
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("average_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contact_person", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("is_walk_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_index("ix_customers_phone", "customers", ["phone"])


def downgrade() -> None:
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_table("stock_balances")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("system_settings")
    op.drop_table("document_sequences")
