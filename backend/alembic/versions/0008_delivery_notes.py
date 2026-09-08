"""delivery_notes + delivery_note_items (fulfillment tracking; no stock mutation)

Revision ID: 0008_delivery_notes
Revises: 0007_uoms
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_delivery_notes"
down_revision = "0007_uoms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_no", sa.String(50), nullable=False, unique=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_no", sa.String(50), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delivery_name", sa.String(200), nullable=True),
        sa.Column("delivery_phone", sa.String(50), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("driver_name", sa.String(200), nullable=True),
        sa.Column("vehicle_note", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_delivery_notes_status", "delivery_notes", ["status"])
    op.create_index("ix_delivery_notes_customer_id", "delivery_notes", ["customer_id"])
    op.create_index("ix_delivery_notes_sale_id", "delivery_notes", ["sale_id"])
    op.create_index("ix_delivery_notes_created_at", "delivery_notes", ["created_at"])

    op.create_table(
        "delivery_note_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_notes.id", ondelete="CASCADE"),
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
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("uom_symbol", sa.String(20), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_to_deliver", sa.Numeric(18, 4), nullable=False),
        sa.Column("qty_delivered", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )
    op.create_index("ix_delivery_note_items_delivery_note_id", "delivery_note_items", ["delivery_note_id"])
    op.create_index("ix_delivery_note_items_sale_item_id", "delivery_note_items", ["sale_item_id"])


def downgrade() -> None:
    op.drop_index("ix_delivery_note_items_sale_item_id", table_name="delivery_note_items")
    op.drop_index("ix_delivery_note_items_delivery_note_id", table_name="delivery_note_items")
    op.drop_table("delivery_note_items")
    op.drop_index("ix_delivery_notes_created_at", table_name="delivery_notes")
    op.drop_index("ix_delivery_notes_sale_id", table_name="delivery_notes")
    op.drop_index("ix_delivery_notes_customer_id", table_name="delivery_notes")
    op.drop_index("ix_delivery_notes_status", table_name="delivery_notes")
    op.drop_table("delivery_notes")
