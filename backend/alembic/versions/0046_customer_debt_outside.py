"""Allow customer debts that were not created by an invoice (outside debt).

POS checkout can record a debt the customer already owed before using the
system (a paper debt book, another shop, an older purchase). Such a row has no
source sale, so ``customer_debts.sale_id`` becomes nullable — ``sale_id IS
NULL`` is what marks a debt as "recorded outside the invoice flow".

``invoice_no`` keeps a generated reference so every report/receipt still shows
a document number: the new ``OUTSIDE_DEBT`` sequence (prefix ``OD``) allocates
``OD-000001`` style values.

``created_by`` records the user who entered the debt, so reports can attribute a
debt that has no source sale to its cashier (invoice debts keep using the sale's
cashier).

Downgrade restores the NOT NULL constraint, so outside debts must be deleted
first (their payments keep their history: ``payments.customer_debt_id`` is
``ON DELETE SET NULL``).

Revision ID: 0046_customer_debt_outside
Revises: 0045_money_4_decimals_all
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_customer_debt_outside"
down_revision = "0045_money_4_decimals_all"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "customer_debts",
        "sale_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "customer_debts",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Existing rows: attribute them to the cashier of their source sale.
    op.execute(
        """
        UPDATE customer_debts AS d
        SET created_by = s.cashier_id
        FROM sales AS s
        WHERE s.id = d.sale_id AND d.created_by IS NULL
        """
    )
    # Document sequence for outside debts (self-healing at runtime too).
    op.execute(
        """
        INSERT INTO document_sequences (id, document_type, prefix, next_number, number_length, status)
        SELECT gen_random_uuid(), 'OUTSIDE_DEBT', 'OD', 1, 6, 'ACTIVE'
        WHERE NOT EXISTS (
            SELECT 1 FROM document_sequences WHERE document_type = 'OUTSIDE_DEBT'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM document_sequences WHERE document_type = 'OUTSIDE_DEBT'")
    op.execute("DELETE FROM customer_debts WHERE sale_id IS NULL")
    op.drop_column("customer_debts", "created_by")
    op.alter_column(
        "customer_debts",
        "sale_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
