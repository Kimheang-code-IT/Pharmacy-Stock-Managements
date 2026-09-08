"""expenses table — operating expenses for the Finance Report (spec 2.1.10)

Revision ID: 0010_expenses
Revises: 0009_telegram_expiry_alerts
Create Date: 2026-09-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_expenses"
down_revision = "0009_telegram_expiry_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_expenses_expense_date", "expenses", ["expense_date"])
    op.create_index("ix_expenses_created_by", "expenses", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_expenses_created_by", table_name="expenses")
    op.drop_index("ix_expenses_expense_date", table_name="expenses")
    op.drop_table("expenses")
