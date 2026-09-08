"""Delivery Notes: multi-invoice links + phone/location header (spec 2.1.9)

- New `delivery_note_sales` table (one delivery note may cover MANY invoices
  of the same customer); legacy single sale_id/invoice_no rows are migrated.
- `delivery_notes.delivery_location` replaces `delivery_address`; the driver/
  vehicle/schedule + receiver-name form fields are dropped (phone + location
  are the only delivery-destination fields).
- `delivery_note_items.sale_id` links every line to its parent sale.

Revision ID: 0013_delivery_multi_invoice
Revises: 0012_auth_profile_extras
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_delivery_multi_invoice"
down_revision = "0012_auth_profile_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Linked-invoices table + data migration from the single-sale header.
    op.create_table(
        "delivery_note_sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_no", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("delivery_note_id", "sale_id", name="uq_delivery_note_sales_note_sale"),
    )
    op.create_index("ix_delivery_note_sales_delivery_note_id", "delivery_note_sales", ["delivery_note_id"])
    op.create_index("ix_delivery_note_sales_sale_id", "delivery_note_sales", ["sale_id"])
    op.execute(
        """
        INSERT INTO delivery_note_sales (id, delivery_note_id, sale_id, invoice_no, created_at)
        SELECT gen_random_uuid(), id, sale_id, invoice_no, created_at
        FROM delivery_notes
        WHERE sale_id IS NOT NULL
        """
    )

    # 2. delivery_location replaces delivery_address (data carried over).
    op.add_column("delivery_notes", sa.Column("delivery_location", sa.Text(), nullable=True))
    op.execute("UPDATE delivery_notes SET delivery_location = delivery_address")

    # 3. Delivery lines link back to their parent sale.
    op.add_column(
        "delivery_note_items",
        sa.Column("sale_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE delivery_note_items items
        SET sale_id = links.sale_id
        FROM delivery_note_sales links
        WHERE links.delivery_note_id = items.delivery_note_id
        """
    )
    op.alter_column("delivery_note_items", "sale_id", nullable=False)
    op.create_foreign_key(
        "fk_delivery_note_items_sale_id",
        "delivery_note_items",
        "sales",
        ["sale_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_delivery_note_items_sale_id", "delivery_note_items", ["sale_id"])

    # 4. Drop the legacy single-sale header + driver/vehicle/schedule UI fields.
    op.drop_index("ix_delivery_notes_sale_id", table_name="delivery_notes")
    op.drop_column("delivery_notes", "sale_id")
    op.drop_column("delivery_notes", "invoice_no")
    op.drop_column("delivery_notes", "delivery_name")
    op.drop_column("delivery_notes", "delivery_address")
    op.drop_column("delivery_notes", "scheduled_date")
    op.drop_column("delivery_notes", "driver_name")
    op.drop_column("delivery_notes", "vehicle_note")


def downgrade() -> None:
    op.add_column(
        "delivery_notes",
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column("delivery_notes", sa.Column("invoice_no", sa.String(50), nullable=True))
    op.add_column("delivery_notes", sa.Column("delivery_name", sa.String(200), nullable=True))
    op.add_column("delivery_notes", sa.Column("delivery_address", sa.Text(), nullable=True))
    op.add_column("delivery_notes", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.add_column("delivery_notes", sa.Column("driver_name", sa.String(200), nullable=True))
    op.add_column("delivery_notes", sa.Column("vehicle_note", sa.String(200), nullable=True))
    op.execute(
        """
        UPDATE delivery_notes note
        SET sale_id = links.sale_id,
            invoice_no = links.invoice_no,
            delivery_address = note.delivery_location
        FROM delivery_note_sales links
        WHERE links.delivery_note_id = note.id
        """
    )
    op.execute("UPDATE delivery_notes SET delivery_name = (SELECT name FROM customers WHERE customers.id = delivery_notes.customer_id)")
    op.drop_index("ix_delivery_note_items_sale_id", table_name="delivery_note_items")
    op.drop_constraint("fk_delivery_note_items_sale_id", "delivery_note_items", type_="foreignkey")
    op.drop_column("delivery_note_items", "sale_id")
    op.drop_column("delivery_notes", "delivery_location")
    op.drop_index("ix_delivery_note_sales_sale_id", table_name="delivery_note_sales")
    op.drop_index("ix_delivery_note_sales_delivery_note_id", "delivery_note_sales")
    op.drop_table("delivery_note_sales")
