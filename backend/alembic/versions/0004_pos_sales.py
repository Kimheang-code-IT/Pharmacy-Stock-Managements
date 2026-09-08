"""pos: sales, sale items, returns, payments, customer debts

Revision ID: 0004_pos_sales
Revises: 0003_stock_transactions
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_pos_sales"
down_revision = "0003_stock_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_no", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("debt_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("payment_status", sa.String(20), nullable=False),
        sa.Column("sale_status", sa.String(20), nullable=False, server_default="COMPLETED"),
        sa.Column(
            "cashier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_pdf_object_key", sa.String(500), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_sale_date", "sales", ["sale_date"])
    op.create_index("ix_sales_customer_id", "sales", ["customer_id"])

    op.create_table(
        "sale_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("returned_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "sale_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("return_no", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("return_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refund_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "sale_return_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_return_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sale_returns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sale_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("refund_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("restock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_no", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payment_type", sa.String(40), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "customer_debts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_no", sa.String(50), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remaining_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="UNPAID"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customer_debts_customer_id", "customer_debts", ["customer_id"])
    op.create_index("ix_customer_debts_status", "customer_debts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_customer_debts_status", table_name="customer_debts")
    op.drop_index("ix_customer_debts_customer_id", table_name="customer_debts")
    op.drop_table("customer_debts")
    op.drop_table("payments")
    op.drop_table("sale_return_items")
    op.drop_table("sale_returns")
    op.drop_table("sale_items")
    op.drop_index("ix_sales_customer_id", table_name="sales")
    op.drop_index("ix_sales_sale_date", table_name="sales")
    op.drop_table("sales")
