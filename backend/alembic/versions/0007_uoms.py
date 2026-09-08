"""units_of_measure + products.uom_id (required) + sale_items uom snapshot

Revision ID: 0007_uoms
Revises: 0006_brands
Create Date: 2026-09-21
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_uoms"
down_revision = "0006_brands"
branch_labels = None
depends_on = None

# Spec section 2.1.3 seed examples.
DEFAULT_UOMS = (
    ("PCS", "Piece", "pcs"),
    ("BOX", "Box", "box"),
    ("CAN", "Can", "can"),
    ("BTL", "Bottle", "btl"),
    ("KG", "Kilogram", "kg"),
    ("PACK", "Pack", "pack"),
)


def upgrade() -> None:
    op.create_table(
        "units_of_measure",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_units_of_measure_code"),
    )

    # Seed default UOMs.
    op.bulk_insert(
        sa.table(
            "units_of_measure",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("symbol", sa.String),
            sa.column("status", sa.String),
        ),
        [
            {
                "id": uuid.uuid4(),
                "code": code,
                "name": name,
                "symbol": symbol,
                "status": "ACTIVE",
            }
            for code, name, symbol in DEFAULT_UOMS
        ],
    )

    # products.uom_id: add nullable, backfill from PCS, then enforce NOT NULL.
    op.add_column(
        "products",
        sa.Column("uom_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE products
        SET uom_id = u.id
        FROM units_of_measure u
        WHERE u.code = 'PCS'
          AND products.uom_id IS NULL
        """
    )
    # Any product still without a UOM falls back to the first seeded UOM.
    op.execute(
        """
        UPDATE products
        SET uom_id = (
            SELECT u.id FROM units_of_measure u
            ORDER BY u.code
            LIMIT 1
        )
        WHERE products.uom_id IS NULL
        """
    )
    op.alter_column("products", "uom_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_products_uom_id",
        "products",
        "units_of_measure",
        ["uom_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_products_uom_id", "products", ["uom_id"])

    # Sale item UOM snapshot (display-only; spec section 2.1.3).
    op.add_column("sale_items", sa.Column("uom_code", sa.String(50), nullable=True))
    op.add_column("sale_items", sa.Column("uom_symbol", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("sale_items", "uom_symbol")
    op.drop_column("sale_items", "uom_code")
    op.drop_index("ix_products_uom_id", table_name="products")
    op.drop_constraint("fk_products_uom_id", "products", type_="foreignkey")
    op.drop_column("products", "uom_id")
    op.drop_table("units_of_measure")
