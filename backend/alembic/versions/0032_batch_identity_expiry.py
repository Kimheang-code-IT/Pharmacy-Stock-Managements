"""batch identity = product + batch_no + expiry_date

The same supplier batch number received with a different expiry date is now a
DISTINCT lot, so a stock-in with a different expiry automatically shows as its
own batch on the product's Batches tab. The unique key becomes a functional
index over (product_id, batch_no, COALESCE(expiry_date, DATE '0001-01-01')) so
lots without an expiry still dedupe NULL-safely.

Revision ID: 0032_batch_identity_expiry
Revises: 0031_product_delete_snapshots
Create Date: 2026-09-20
"""

from alembic import op

revision = "0032_batch_identity_expiry"
down_revision = "0031_product_delete_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_batch_stock_balances", "batch_stock_balances", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX uq_batch_stock_balances ON batch_stock_balances "
        "(product_id, batch_no, COALESCE(expiry_date, DATE '0001-01-01'))"
    )


def downgrade() -> None:
    # Fails if a batch_no now has multiple lots (different expiries); that data
    # cannot collapse back into the old (product_id, batch_no) uniqueness.
    op.execute("DROP INDEX uq_batch_stock_balances")
    op.create_unique_constraint(
        "uq_batch_stock_balances", "batch_stock_balances", ["product_id", "batch_no"]
    )
