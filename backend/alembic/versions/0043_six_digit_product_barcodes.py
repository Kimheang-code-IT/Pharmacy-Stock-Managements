"""Convert product identifiers to unique six-digit internal barcodes.

The old-to-new mapping is retained in product_barcode_migration_0043 so the
change is auditable and downgrade can restore the original identifiers.
Historical sale_items.barcode snapshots are deliberately not rewritten.

Revision ID: 0043_six_digit_product_barcodes
Revises: 0042_archive_and_remove_legacy
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_six_digit_product_barcodes"
down_revision = "0042_archive_and_remove_legacy"
branch_labels = None
depends_on = None

BARCODE_MIN = 100_001
BARCODE_MAX = 999_999
BARCODE_CAPACITY = BARCODE_MAX - BARCODE_MIN + 1


def barcode_for_position(position: int) -> str:
    if position < 1 or position > BARCODE_CAPACITY:
        raise ValueError("Six-digit internal barcode range is exhausted")
    return f"{BARCODE_MIN + position - 1:06d}"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE products IN ACCESS EXCLUSIVE MODE"))
    product_count = bind.scalar(sa.text("SELECT count(*) FROM products")) or 0
    if product_count > BARCODE_CAPACITY:
        raise RuntimeError(
            f"Cannot migrate {product_count} products into {BARCODE_CAPACITY} internal barcodes"
        )

    op.create_table(
        "product_barcode_migration_0043",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("old_barcode", sa.String(length=100), nullable=False),
        sa.Column("new_barcode", sa.String(length=6), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("product_id"),
        sa.UniqueConstraint("old_barcode"),
        sa.UniqueConstraint("new_barcode"),
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO product_barcode_migration_0043 (product_id, old_barcode, new_barcode)
            SELECT id, barcode,
                   lpad((CAST(:base AS bigint) + row_number() OVER (ORDER BY created_at, id))::text, 6, '0')
            FROM products
            """
        ),
        {"base": BARCODE_MIN - 1},
    )
    # Temporary UUID-based values avoid transient UNIQUE conflicts where an
    # old barcode already equals another product's assigned six-digit value.
    bind.execute(
        sa.text("UPDATE products SET barcode = '__0043__' || id::text")
    )
    bind.execute(
        sa.text(
            """
            UPDATE products AS p
            SET barcode = m.new_barcode
            FROM product_barcode_migration_0043 AS m
            WHERE m.product_id = p.id
            """
        )
    )
    op.alter_column("products", "barcode", type_=sa.String(length=6), existing_nullable=False)
    op.create_check_constraint(
        "ck_products_barcode_six_digits",
        "products",
        "barcode ~ '^[0-9]{6}$'",
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE products IN ACCESS EXCLUSIVE MODE"))
    op.drop_constraint("ck_products_barcode_six_digits", "products", type_="check")
    op.alter_column("products", "barcode", type_=sa.String(length=100), existing_nullable=False)
    bind.execute(
        sa.text(
            """
            UPDATE products AS p
            SET barcode = '__0043_rollback__' || p.id::text
            FROM product_barcode_migration_0043 AS m
            WHERE m.product_id = p.id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE products AS p
            SET barcode = m.old_barcode
            FROM product_barcode_migration_0043 AS m
            WHERE m.product_id = p.id
            """
        )
    )
    op.drop_table("product_barcode_migration_0043")
