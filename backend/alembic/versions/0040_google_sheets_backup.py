"""Google Sheets backup bookkeeping.

Adds four tables used by the automatic Google Sheets backup feature:

- `backup_jobs` / `backup_job_tables` — one row per run and per table so the
  Settings UI can show a success/failure history.
- `backup_records` — the last backed-up version + row hash per source record,
  used to detect new/changed rows and to prevent duplicate appends.
- `backup_table_states` — the column set last written per table so a future
  schema change (new column) updates the sheet header.

The `system.backup` / `system.restore` permissions already exist (0036).

Revision ID: 0040_google_sheets_backup
Revises: 0039_drop_product_sku
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_google_sheets_backup"
down_revision = "0039_drop_product_sku"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tables_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tables_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tables_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_appended", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_backup_jobs_started_at", "backup_jobs", ["started_at"])

    op.create_table(
        "backup_job_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("table_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("rows_appended", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["backup_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_backup_job_tables_job_id", "backup_job_tables", ["job_id"])

    op.create_table(
        "backup_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_name", sa.String(255), nullable=False),
        sa.Column("record_id", sa.String(512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("hashed_columns", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "first_backed_up_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_backed_up_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("table_name", "record_id", name="uq_backup_records_table_record"),
    )
    op.create_index("ix_backup_records_table_name", "backup_records", ["table_name"])

    op.create_table(
        "backup_table_states",
        sa.Column("table_name", sa.String(255), primary_key=True),
        sa.Column("columns", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("header_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_backup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_row_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("backup_table_states")
    op.drop_index("ix_backup_records_table_name", table_name="backup_records")
    op.drop_table("backup_records")
    op.drop_index("ix_backup_job_tables_job_id", table_name="backup_job_tables")
    op.drop_table("backup_job_tables")
    op.drop_index("ix_backup_jobs_started_at", table_name="backup_jobs")
    op.drop_table("backup_jobs")
