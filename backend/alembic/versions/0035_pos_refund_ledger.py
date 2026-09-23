"""POS permissions + sale-return refund ledger.

- Permission catalog gains pos.sale_edit, pos.return and pos.refund. They are
  backfilled onto every role that already held pos.access so existing cashier
  roles keep working; Administrators keep the ALL_PAGES wildcard.
- sale_returns becomes a real refund ledger: disposition, method, amount paid,
  credit amount, debt reduction, reference, note, processor and a document
  currency/exchange-rate snapshot.
- payments gains sale_return_id so a cash/bank refund is an auditable cash-out
  row (payment_type=SALE_REFUND).
- A SALE_REFUND document sequence is added.

Existing returns are classified conservatively: a return against a sale that
has a customer-debt row is marked DEBT_REDUCTION (matching the legacy behavior
that only reduced debt) and everything else NO_REFUND. No cash movement is ever
fabricated for historical rows (refund_paid_amount stays 0).

Revision ID: 0035_pos_refund_ledger
Revises: 0034_batch_pricing_snapshots
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_pos_refund_ledger"
down_revision = "0034_batch_pricing_snapshots"
branch_labels = None
depends_on = None

_NEW_POS_PERMISSIONS = (
    ("pos.sale_edit", "sale_edit"),
    ("pos.return", "return"),
    ("pos.refund", "refund"),
)


def upgrade() -> None:
    # 1. Sale-return refund ledger columns.
    op.add_column(
        "sale_returns",
        sa.Column("status", sa.String(20), nullable=False, server_default="COMPLETED"),
    )
    op.add_column("sale_returns", sa.Column("refund_disposition", sa.String(30), nullable=True))
    op.add_column("sale_returns", sa.Column("refund_method", sa.String(30), nullable=True))
    op.add_column(
        "sale_returns",
        sa.Column("refund_paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "sale_returns",
        sa.Column("credit_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "sale_returns",
        sa.Column("debt_reduction", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column("sale_returns", sa.Column("refund_reference", sa.String(100), nullable=True))
    op.add_column("sale_returns", sa.Column("refund_note", sa.Text(), nullable=True))
    op.add_column(
        "sale_returns",
        sa.Column("processed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sale_returns",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sale_returns",
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
    )
    op.add_column(
        "sale_returns",
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "sale_returns_processed_by_fkey",
        "sale_returns",
        "users",
        ["processed_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Payment -> return link (cash/bank refund rows).
    op.add_column(
        "payments",
        sa.Column("sale_return_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "payments_sale_return_id_fkey",
        "payments",
        "sale_returns",
        ["sale_return_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Backfill historical returns conservatively (no invented cash).
    op.execute(
        "UPDATE sale_returns r SET "
        "  currency = COALESCE(s.currency, 'USD'), "
        "  exchange_rate = COALESCE(s.exchange_rate, 1), "
        "  processed_by = r.created_by, "
        "  processed_at = r.return_date, "
        "  refund_disposition = CASE "
        "    WHEN EXISTS (SELECT 1 FROM customer_debts d WHERE d.sale_id = r.sale_id) "
        "      THEN 'DEBT_REDUCTION' ELSE 'NO_REFUND' END, "
        "  debt_reduction = CASE "
        "    WHEN EXISTS (SELECT 1 FROM customer_debts d WHERE d.sale_id = r.sale_id) "
        "      THEN r.refund_amount ELSE 0 END "
        "FROM sales s WHERE s.id = r.sale_id"
    )

    # 4. New POS permission catalog rows (idempotent).
    op.execute(
        """
        INSERT INTO permissions (id, code, module, action, description)
        SELECT gen_random_uuid(), v.code, 'pos', v.action, NULL
        FROM (
            VALUES ('pos.sale_edit', 'sale_edit'),
                   ('pos.return', 'return'),
                   ('pos.refund', 'refund')
        ) AS v(code, action)
        WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code)
        """
    )
    # 4b. Preserve existing behavior: any role that could create/return a sale
    #     via pos.access keeps its edit/return/refund ability until an admin
    #     revokes it on the Roles matrix.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT pa.role_id, np.id
        FROM role_permissions pa
        JOIN permissions access ON access.id = pa.permission_id AND access.code = 'pos.access'
        JOIN permissions np ON np.code IN ('pos.sale_edit', 'pos.return', 'pos.refund')
        ON CONFLICT DO NOTHING
        """
    )

    # 5. SALE_REFUND document sequence.
    op.execute(
        """
        INSERT INTO document_sequences (id, document_type, prefix, next_number, number_length, status)
        SELECT gen_random_uuid(), 'SALE_REFUND', 'SRF', 1, 6, 'ACTIVE'
        WHERE NOT EXISTS (
            SELECT 1 FROM document_sequences WHERE document_type = 'SALE_REFUND'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM document_sequences WHERE document_type = 'SALE_REFUND'")

    # Remove the new permission grants + catalog rows.
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions
            WHERE code IN ('pos.sale_edit', 'pos.return', 'pos.refund')
        )
        """
    )
    op.execute(
        "DELETE FROM permissions WHERE code IN ('pos.sale_edit', 'pos.return', 'pos.refund')"
    )

    op.drop_constraint("payments_sale_return_id_fkey", "payments", type_="foreignkey")
    op.drop_column("payments", "sale_return_id")

    op.drop_constraint("sale_returns_processed_by_fkey", "sale_returns", type_="foreignkey")
    for column in (
        "exchange_rate",
        "currency",
        "processed_at",
        "processed_by",
        "refund_note",
        "refund_reference",
        "debt_reduction",
        "credit_amount",
        "refund_paid_amount",
        "refund_method",
        "refund_disposition",
        "status",
    ):
        op.drop_column("sale_returns", column)
