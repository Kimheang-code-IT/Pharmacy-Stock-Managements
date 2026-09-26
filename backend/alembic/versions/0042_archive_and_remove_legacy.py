"""Archive and remove legacy cash-register, stock-count and telegram-template objects.

Stage-2 cleanup of orphaned objects that are not mapped by the ORM, not created
by any migration, and referenced by no source/API/report/job (see
`database_cleanup_report.md` and `database_cleanup_report_stage1_5.md`).

Portability: these tables/columns were never created by an Alembic migration,
so they may be absent on a fresh database. Every step is existence-guarded, so
`upgrade()` and `downgrade()` are safe on:
- an existing database that still has the legacy objects (archive + drop), and
- a fresh database built from migrations (no-op for the legacy objects).

Safety:
- On a database that has the legacy tables, each is copied into
  `legacy_archive_<name>` BEFORE being dropped, so `downgrade()` restores
  structure AND data. A verified `pg_dump` is additionally required
  (db_archive/).
- No application code changes are needed: the dropped objects were unmapped.

Revision ID: 0042_archive_and_remove_legacy
Revises: 0041_add_backup_schema_version
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import bindparam
from sqlalchemy.dialects import postgresql

revision = "0042_archive_and_remove_legacy"
down_revision = "0041_add_backup_schema_version"
branch_labels = None
depends_on = None

# Drop order: children before parents.
DROP_ORDER = (
    "register_cash_movements",
    "stock_count_items",
    "stock_counts",
    "register_shifts",
    "telegram_message_templates",
)
# Create order: parents before children.
CREATE_ORDER = (
    "register_shifts",
    "register_cash_movements",
    "stock_counts",
    "stock_count_items",
    "telegram_message_templates",
)

SHIFT_TABLES = ("sales", "payments", "expenses")

STALE_PERMISSIONS = (
    "register.open",
    "register.close",
    "register.adjust",
    "register.view",
    "report.register",
    "stock.count",
    "stock.count_approve",
)
STALE_SEQUENCES = (
    ("REGISTER_SHIFT", "RSH", 2),
    ("STOCK_COUNT", "STC", 2),
)

# Exact DDL captured from the pre-cleanup schema (pg_dump -s), used only by
# downgrade() to recreate the tables verbatim.
RECREATE: dict[str, tuple[str, ...]] = {
    "register_shifts": (
        """CREATE TABLE IF NOT EXISTS public.register_shifts (
            id uuid NOT NULL,
            shift_no character varying(50) NOT NULL,
            cashier_id uuid NOT NULL,
            status character varying(20) DEFAULT 'OPEN'::character varying NOT NULL,
            currency character varying(10) DEFAULT 'USD'::character varying NOT NULL,
            exchange_rate numeric(18,6) DEFAULT '1'::numeric NOT NULL,
            opening_cash numeric(18,2) DEFAULT '0'::numeric NOT NULL,
            expected_cash numeric(18,2),
            actual_cash numeric(18,2),
            difference numeric(18,2),
            opening_note text,
            closing_note text,
            opened_by uuid NOT NULL,
            opened_at timestamp with time zone DEFAULT now() NOT NULL,
            closed_by uuid,
            closed_at timestamp with time zone
        )""",
        "ALTER TABLE ONLY public.register_shifts ADD CONSTRAINT register_shifts_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY public.register_shifts ADD CONSTRAINT register_shifts_shift_no_key UNIQUE (shift_no)",
        "CREATE INDEX ix_register_shifts_cashier_status ON public.register_shifts USING btree (cashier_id, status)",
        "CREATE INDEX ix_register_shifts_opened_at ON public.register_shifts USING btree (opened_at)",
        "CREATE UNIQUE INDEX ux_register_shifts_one_open ON public.register_shifts USING btree (cashier_id) WHERE ((status)::text = 'OPEN'::text)",
        "ALTER TABLE ONLY public.register_shifts ADD CONSTRAINT register_shifts_cashier_id_fkey FOREIGN KEY (cashier_id) REFERENCES public.users(id) ON DELETE RESTRICT",
        "ALTER TABLE ONLY public.register_shifts ADD CONSTRAINT register_shifts_opened_by_fkey FOREIGN KEY (opened_by) REFERENCES public.users(id) ON DELETE RESTRICT",
        "ALTER TABLE ONLY public.register_shifts ADD CONSTRAINT register_shifts_closed_by_fkey FOREIGN KEY (closed_by) REFERENCES public.users(id) ON DELETE SET NULL",
    ),
    "register_cash_movements": (
        """CREATE TABLE IF NOT EXISTS public.register_cash_movements (
            id uuid NOT NULL,
            shift_id uuid NOT NULL,
            movement_type character varying(40) NOT NULL,
            direction character varying(10) NOT NULL,
            is_cash boolean DEFAULT true NOT NULL,
            amount numeric(18,2) NOT NULL,
            currency character varying(10) DEFAULT 'USD'::character varying NOT NULL,
            exchange_rate numeric(18,6) DEFAULT '1'::numeric NOT NULL,
            source_type character varying(40),
            source_id uuid,
            note text,
            created_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        )""",
        "ALTER TABLE ONLY public.register_cash_movements ADD CONSTRAINT register_cash_movements_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_register_cash_movements_shift_id ON public.register_cash_movements USING btree (shift_id)",
        "CREATE INDEX ix_register_cash_movements_source ON public.register_cash_movements USING btree (source_type, source_id)",
        "ALTER TABLE ONLY public.register_cash_movements ADD CONSTRAINT register_cash_movements_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES public.register_shifts(id) ON DELETE CASCADE",
        "ALTER TABLE ONLY public.register_cash_movements ADD CONSTRAINT register_cash_movements_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL",
    ),
    "stock_counts": (
        """CREATE TABLE IF NOT EXISTS public.stock_counts (
            id uuid NOT NULL,
            count_no character varying(50) NOT NULL,
            status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
            note text,
            created_by uuid NOT NULL,
            counted_by uuid,
            approved_by uuid,
            posted_by uuid,
            counted_at timestamp with time zone,
            approved_at timestamp with time zone,
            posted_at timestamp with time zone,
            cancel_reason text,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        )""",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_count_no_key UNIQUE (count_no)",
        "CREATE INDEX ix_stock_counts_created_at ON public.stock_counts USING btree (created_at)",
        "CREATE INDEX ix_stock_counts_status ON public.stock_counts USING btree (status)",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_counted_by_fkey FOREIGN KEY (counted_by) REFERENCES public.users(id) ON DELETE SET NULL",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL",
        "ALTER TABLE ONLY public.stock_counts ADD CONSTRAINT stock_counts_posted_by_fkey FOREIGN KEY (posted_by) REFERENCES public.users(id) ON DELETE SET NULL",
    ),
    "stock_count_items": (
        """CREATE TABLE IF NOT EXISTS public.stock_count_items (
            id uuid NOT NULL,
            stock_count_id uuid NOT NULL,
            product_id uuid,
            product_name character varying(200),
            system_quantity numeric(18,4) DEFAULT '0'::numeric NOT NULL,
            actual_quantity numeric(18,4),
            variance numeric(18,4),
            unit_cost numeric(18,2) DEFAULT '0'::numeric NOT NULL,
            note text,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        )""",
        "ALTER TABLE ONLY public.stock_count_items ADD CONSTRAINT stock_count_items_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_stock_count_items_count_id ON public.stock_count_items USING btree (stock_count_id)",
        "ALTER TABLE ONLY public.stock_count_items ADD CONSTRAINT stock_count_items_stock_count_id_fkey FOREIGN KEY (stock_count_id) REFERENCES public.stock_counts(id) ON DELETE CASCADE",
        "ALTER TABLE ONLY public.stock_count_items ADD CONSTRAINT stock_count_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE SET NULL",
    ),
    "telegram_message_templates": (
        """CREATE TABLE IF NOT EXISTS public.telegram_message_templates (
            id uuid NOT NULL,
            key character varying(100) NOT NULL,
            body_en text NOT NULL,
            body_km text NOT NULL,
            is_enabled boolean DEFAULT true NOT NULL,
            updated_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL
        )""",
        "ALTER TABLE ONLY public.telegram_message_templates ADD CONSTRAINT telegram_message_templates_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY public.telegram_message_templates ADD CONSTRAINT telegram_message_templates_key_key UNIQUE (key)",
        "ALTER TABLE ONLY public.telegram_message_templates ADD CONSTRAINT telegram_message_templates_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL",
    ),
}


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return bind.execute(
        sa.text("SELECT to_regclass(:n)"), {"n": f"public.{name}"}
    ).scalar() is not None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).scalar() is not None


def upgrade() -> None:
    # 1) Preserve the legacy rows in-DB before dropping anything (only if present).
    for table in DROP_ORDER:
        if _table_exists(table):
            op.execute(f"CREATE TABLE legacy_archive_{table} AS TABLE public.{table}")

    # 2) Drop the incoming FK columns on live tables (only if present).
    for table in SHIFT_TABLES:
        if _column_exists(table, "shift_id"):
            op.drop_column(table, "shift_id")

    # 3) Drop the legacy tables (children first; absent on fresh databases).
    for table in DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS public.{table}")

    # 4) Remove stale catalogue / sequence / backup-bookkeeping rows.
    op.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            bindparam("codes", value=list(STALE_PERMISSIONS), expanding=True)
        )
    )
    op.execute(
        sa.text("DELETE FROM document_sequences WHERE document_type IN :types").bindparams(
            bindparam("types", value=[row[0] for row in STALE_SEQUENCES], expanding=True)
        )
    )
    op.execute(
        sa.text("DELETE FROM backup_records WHERE table_name IN :tables").bindparams(
            bindparam("tables", value=list(DROP_ORDER), expanding=True)
        )
    )
    op.execute(
        sa.text("DELETE FROM backup_table_states WHERE table_name IN :tables").bindparams(
            bindparam("tables", value=list(DROP_ORDER), expanding=True)
        )
    )


def downgrade() -> None:
    # 1) Recreate the legacy tables verbatim (parents first) if missing.
    for table in CREATE_ORDER:
        if not _table_exists(table):
            for statement in RECREATE[table]:
                op.execute(statement)

    # 2) Recreate the shift_id columns + FKs on the live tables if missing.
    for table in SHIFT_TABLES:
        if not _column_exists(table, "shift_id"):
            op.add_column(
                table,
                sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
            op.create_foreign_key(
                f"{table}_shift_id_fkey",
                table,
                "register_shifts",
                ["shift_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # 3) Restore the archived rows (only where an archive exists).
    for table in CREATE_ORDER:
        if _table_exists(f"legacy_archive_{table}"):
            op.execute(f"INSERT INTO public.{table} SELECT * FROM legacy_archive_{table}")

    # 4) Restore the stale permission / document-sequence rows.
    for code in STALE_PERMISSIONS:
        module, action = code.rsplit(".", 1)
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, module, action) "
                "VALUES (gen_random_uuid(), :code, :module, :action) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, module=module, action=action)
        )
    for document_type, prefix, next_number in STALE_SEQUENCES:
        op.execute(
            sa.text(
                "INSERT INTO document_sequences "
                "(id, document_type, prefix, next_number, number_length, status) "
                "VALUES (gen_random_uuid(), :document_type, :prefix, :next_number, 6, 'ACTIVE') "
                "ON CONFLICT (document_type) DO NOTHING"
            ).bindparams(document_type=document_type, prefix=prefix, next_number=next_number)
        )

    # 5) The archive has been drained back into the real tables.
    for table in DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS legacy_archive_{table}")
