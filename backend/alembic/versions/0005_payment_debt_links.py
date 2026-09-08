"""payments: per-debt links for immutable debt payment history

Revision ID: 0005_payment_debt_links
Revises: 0004_pos_sales
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_payment_debt_links"
down_revision = "0004_pos_sales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("customer_debt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("supplier_debt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_customer_debt_id", "payments", "customer_debts", ["customer_debt_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_payments_supplier_debt_id", "payments", "supplier_debts", ["supplier_debt_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_payments_customer_debt_id", "payments", ["customer_debt_id"])
    op.create_index("ix_payments_supplier_debt_id", "payments", ["supplier_debt_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_supplier_debt_id", table_name="payments")
    op.drop_index("ix_payments_customer_debt_id", table_name="payments")
    op.drop_constraint("fk_payments_supplier_debt_id", "payments", type_="foreignkey")
    op.drop_constraint("fk_payments_customer_debt_id", "payments", type_="foreignkey")
    op.drop_column("payments", "supplier_debt_id")
    op.drop_column("payments", "customer_debt_id")
