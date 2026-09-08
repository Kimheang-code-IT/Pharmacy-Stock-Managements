"""stock transactions, items, movements, supplier debts

Revision ID: 0003_stock_transactions
Revises: 0002_master_data
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_stock_transactions"
down_revision = "0002_master_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_no", sa.String(50), nullable=False, unique=True),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_stock_transactions_created_at", "stock_transactions", ["transaction_date"])

    op.create_table(
        "stock_transaction_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stock_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("system_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("actual_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(30), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_no", sa.String(50), nullable=True),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    op.create_table(
        "supplier_debts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "stock_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_no", sa.String(50), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remaining_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="UNPAID"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_supplier_debts_supplier_id", "supplier_debts", ["supplier_id"])
    op.create_index("ix_supplier_debts_status", "supplier_debts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_supplier_debts_status", table_name="supplier_debts")
    op.drop_index("ix_supplier_debts_supplier_id", table_name="supplier_debts")
    op.drop_table("supplier_debts")
    op.drop_index("ix_stock_movements_created_at", table_name="stock_movements")
    op.drop_index("ix_stock_movements_product_id", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("stock_transaction_items")
    op.drop_index("ix_stock_transactions_created_at", table_name="stock_transactions")
    op.drop_table("stock_transactions")
