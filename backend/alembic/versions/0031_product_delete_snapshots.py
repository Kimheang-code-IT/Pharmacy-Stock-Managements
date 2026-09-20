"""product hard-delete: keep history via snapshots and SET NULL links

Products can now be hard-deleted even when purchase/sale/return/delivery history
exists. History rows keep the product name (and sku where shown) through
snapshot columns, and their product_id foreign keys become nullable with
ON DELETE SET NULL so the product row can go without deleting the history.

- stock_transaction_items: + product_name, sku
- stock_movements: + product_name
- sale_return_items: + product_name
- purchase_return_items: + product_name
- sale_items / sale_return_items / delivery_note_items / stock_transaction_items
  / stock_movements / purchase_return_items: product_id -> SET NULL (nullable)
- telegram_expiry_alert_state: product_id -> CASCADE (dedupe state, not history)

Revision ID: 0031_product_delete_snapshots
Revises: 0030_user_telegram_name
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_product_delete_snapshots"
down_revision = "0030_user_telegram_name"
branch_labels = None
depends_on = None

# History tables whose product link becomes nullable + ON DELETE SET NULL.
_SET_NULL_TABLES = (
    "sale_items",
    "sale_return_items",
    "delivery_note_items",
    "stock_transaction_items",
    "stock_movements",
    "purchase_return_items",
)


def _product_fk_name(table: str) -> str:
    return f"{table}_product_id_fkey"


def upgrade() -> None:
    # 1. Snapshot columns so history keeps the product identity after deletion.
    op.add_column("stock_transaction_items", sa.Column("product_name", sa.String(200), nullable=True))
    op.add_column("stock_transaction_items", sa.Column("sku", sa.String(100), nullable=True))
    op.add_column("stock_movements", sa.Column("product_name", sa.String(200), nullable=True))
    op.add_column("sale_return_items", sa.Column("product_name", sa.String(200), nullable=True))
    op.add_column("purchase_return_items", sa.Column("product_name", sa.String(200), nullable=True))

    # 2. Backfill existing history rows from the products table.
    op.execute(
        "UPDATE stock_transaction_items i SET product_name = p.name, sku = p.sku "
        "FROM products p WHERE p.id = i.product_id AND i.product_name IS NULL"
    )
    op.execute(
        "UPDATE stock_movements m SET product_name = p.name "
        "FROM products p WHERE p.id = m.product_id AND m.product_name IS NULL"
    )
    op.execute(
        "UPDATE sale_return_items r SET product_name = p.name "
        "FROM products p WHERE p.id = r.product_id AND r.product_name IS NULL"
    )
    op.execute(
        "UPDATE purchase_return_items r SET product_name = p.name "
        "FROM products p WHERE p.id = r.product_id AND r.product_name IS NULL"
    )

    # 3. product_id -> SET NULL for history tables.
    for table in _SET_NULL_TABLES:
        op.drop_constraint(_product_fk_name(table), table, type_="foreignkey")
        op.alter_column(
            table,
            "product_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
        op.create_foreign_key(
            _product_fk_name(table),
            table,
            "products",
            ["product_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 3b. batch_stock_balances is removed with the product (CASCADE), so history
    #     rows that point at a lot must become NULL instead of RESTRICT.
    op.drop_constraint("fk_stock_movements_batch_id", "stock_movements", type_="foreignkey")
    op.create_foreign_key(
        "fk_stock_movements_batch_id",
        "stock_movements",
        "batch_stock_balances",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("sale_item_batches_batch_id_fkey", "sale_item_batches", type_="foreignkey")
    op.alter_column(
        "sale_item_batches",
        "batch_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "sale_item_batches_batch_id_fkey",
        "sale_item_batches",
        "batch_stock_balances",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. Expiry alert state is dedupe state, not history: drop with the product.
    op.drop_constraint(
        "telegram_expiry_alert_state_product_id_fkey",
        "telegram_expiry_alert_state",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "telegram_expiry_alert_state_product_id_fkey",
        "telegram_expiry_alert_state",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Restore RESTRICT product links. Fails if products were deleted while
    # history rows remain (their product_id is NULL and cannot be filled).
    op.drop_constraint(
        "telegram_expiry_alert_state_product_id_fkey",
        "telegram_expiry_alert_state",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "telegram_expiry_alert_state_product_id_fkey",
        "telegram_expiry_alert_state",
        "products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for table in _SET_NULL_TABLES:
        op.drop_constraint(_product_fk_name(table), table, type_="foreignkey")
        op.alter_column(
            table,
            "product_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
        op.create_foreign_key(
            _product_fk_name(table),
            table,
            "products",
            ["product_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_constraint("sale_item_batches_batch_id_fkey", "sale_item_batches", type_="foreignkey")
    op.alter_column(
        "sale_item_batches",
        "batch_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "sale_item_batches_batch_id_fkey",
        "sale_item_batches",
        "batch_stock_balances",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("fk_stock_movements_batch_id", "stock_movements", type_="foreignkey")
    op.create_foreign_key(
        "fk_stock_movements_batch_id",
        "stock_movements",
        "batch_stock_balances",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_column("purchase_return_items", "product_name")
    op.drop_column("sale_return_items", "product_name")
    op.drop_column("stock_movements", "product_name")
    op.drop_column("stock_transaction_items", "sku")
    op.drop_column("stock_transaction_items", "product_name")
