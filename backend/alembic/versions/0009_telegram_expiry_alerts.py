"""telegram_expiry_alert_state (spec section 3.6) — dedupe expiry alert sends

Revision ID: 0009_telegram_expiry_alerts
Revises: 0008_delivery_notes
Create Date: 2026-09-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_telegram_expiry_alerts"
down_revision = "0008_delivery_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_expiry_alert_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("alert_level", sa.SmallInteger(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Spec UNIQUE (product_id, batch_no, expiry_date, alert_level). batch_no is
    # nullable, so the enforcing index coalesces it to '' (PostgreSQL treats
    # NULLs as distinct in plain unique constraints, which would not dedupe
    # unbatched lots).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_telegram_expiry_alert_state_lot
        ON telegram_expiry_alert_state (
            product_id,
            COALESCE(batch_no, ''),
            expiry_date,
            alert_level
        )
        """
    )
    op.create_index(
        "ix_telegram_expiry_alert_state_product_id",
        "telegram_expiry_alert_state",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_expiry_alert_state_product_id", table_name="telegram_expiry_alert_state")
    op.execute("DROP INDEX IF EXISTS uq_telegram_expiry_alert_state_lot")
    op.drop_table("telegram_expiry_alert_state")
