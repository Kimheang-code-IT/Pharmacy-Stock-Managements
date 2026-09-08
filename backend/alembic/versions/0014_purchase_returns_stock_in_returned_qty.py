"""Purchase returns (return to supplier) + stock-in returned qty + DN NOT NULL.

Revision ID: 0014_purchase_returns
Revises: 0013_delivery_multi_invoice
Create Date: 2026-10-01

- purchase_returns / purchase_return_items: immutable supplier-return
  documents against a confirmed Stock In (spec 4.2, Purchase Return
  Transaction). Stock-out happens via the canonical PURCHASE_RETURN movement.
- stock_transaction_items.returned_quantity: cumulative returned qty (base
  UOM) per stock-in line, mirroring sale_items.returned_quantity.
- delivery_notes.delivery_phone / delivery_location: NOT NULL (spec 2.1.9);
  legacy NULLs are backfilled with empty strings.
- Document sequences: new PURCHASE_RETURN (PRT) default is created lazily by
  the allocator, so no data migration is needed here.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_purchase_returns"
down_revision = "0013_delivery_multi_invoice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("return_no", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "stock_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("return_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refund_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("debt_reduction", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("credit_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_purchase_returns_stock_transaction_id",
        "purchase_returns",
        ["stock_transaction_id"],
    )
    op.create_index("ix_purchase_returns_supplier_id", "purchase_returns", ["supplier_id"])

    op.create_table(
        "purchase_return_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "purchase_return_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_returns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stock_transaction_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_transaction_items.id", ondelete="RESTRICT"),
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
        sa.Column("line_refund", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column(
        "stock_transaction_items",
        sa.Column("returned_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )

    # Line UOM symbol snapshots (display only; quantities stay in base UOM).
    op.add_column(
        "stock_transaction_items",
        sa.Column("uom_symbol", sa.String(20), nullable=True),
    )
    op.add_column(
        "stock_movements",
        sa.Column("uom_symbol", sa.String(20), nullable=True),
    )

    # Document sequences: PURCHASE_RETURN (PRT) default for databases seeded
    # before this revision, and the sale-return prefix re-pointed to SRT.
    op.execute(
        """
        INSERT INTO document_sequences (id, document_type, prefix, next_number, number_length, status)
        SELECT gen_random_uuid(), 'PURCHASE_RETURN', 'PRT', 1, 6, 'ACTIVE'
        WHERE NOT EXISTS (
            SELECT 1 FROM document_sequences WHERE document_type = 'PURCHASE_RETURN'
        )
        """
    )
    op.execute(
        "UPDATE document_sequences SET prefix = 'SRT' "
        "WHERE document_type = 'SALE_RETURN' AND prefix = 'RET'"
    )

    # Delivery destination is mandatory (spec 2.1.9): backfill, then enforce.
    op.execute("UPDATE delivery_notes SET delivery_phone = '' WHERE delivery_phone IS NULL")
    op.execute("UPDATE delivery_notes SET delivery_location = '' WHERE delivery_location IS NULL")
    op.alter_column("delivery_notes", "delivery_phone", nullable=False, server_default="")
    op.alter_column("delivery_notes", "delivery_location", nullable=False, server_default="")


def downgrade() -> None:
    op.alter_column("delivery_notes", "delivery_location", nullable=True)
    op.alter_column("delivery_notes", "delivery_phone", nullable=True)
    op.drop_column("stock_movements", "uom_symbol")
    op.drop_column("stock_transaction_items", "uom_symbol")
    op.drop_column("stock_transaction_items", "returned_quantity")
    op.drop_table("purchase_return_items")
    op.drop_index("ix_purchase_returns_supplier_id", table_name="purchase_returns")
    op.drop_index("ix_purchase_returns_stock_transaction_id", table_name="purchase_returns")
    op.drop_table("purchase_returns")
