"""Expense lifecycle: DRAFT → POSTED → VOID.

- expenses gain a DRAFT/POSTED/VOID lifecycle (approval, posting date, void
  reason, attachment). Existing rows become POSTED with posting_date set.
- New expense permissions and the stock-valuation / expense report codes.

Revision ID: 0037_ops_completeness
Revises: 0036_audit_security
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_ops_completeness"
down_revision = "0036_audit_security"
branch_labels = None
depends_on = None

_NEW_PERMISSIONS = (
    ("expense.view", "expense", "view"),
    ("expense.create", "expense", "create"),
    ("expense.approve", "expense", "approve"),
    ("expense.void", "expense", "void"),
    ("report.stock_valuation", "report", "stock_valuation"),
    ("report.expense", "report", "expense"),
)


def upgrade() -> None:
    # Expense lifecycle.
    op.add_column("expenses", sa.Column("status", sa.String(20), nullable=False, server_default="POSTED"))
    op.add_column("expenses", sa.Column("posting_date", sa.Date(), nullable=True))
    op.add_column("expenses", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("expenses", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("expenses", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("expenses", sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("expenses", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("expenses", sa.Column("attachment_object_key", sa.String(500), nullable=True))
    op.create_foreign_key(
        "expenses_approved_by_fkey", "expenses", "users", ["approved_by"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "expenses_voided_by_fkey", "expenses", "users", ["voided_by"], ["id"], ondelete="SET NULL"
    )
    op.execute("UPDATE expenses SET posting_date = expense_date WHERE posting_date IS NULL")

    # Permission catalog rows (idempotent).
    for code, module, action in _NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, module, action, description) "
                "SELECT gen_random_uuid(), :code, :module, :action, NULL "
                "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"
            ).bindparams(code=code, module=module, action=action)
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM permissions WHERE code IN "
        "('expense.view', 'expense.approve', 'expense.void', "
        "'report.stock_valuation', 'report.expense')"
    )
    op.drop_constraint("expenses_voided_by_fkey", "expenses", type_="foreignkey")
    op.drop_constraint("expenses_approved_by_fkey", "expenses", type_="foreignkey")
    for column in (
        "attachment_object_key",
        "voided_at",
        "voided_by",
        "void_reason",
        "approved_at",
        "approved_by",
        "posting_date",
        "status",
    ):
        op.drop_column("expenses", column)
