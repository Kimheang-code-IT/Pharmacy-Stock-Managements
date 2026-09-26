"""Backup schema version metadata.

Adds the schema/version markers recorded on every Google Sheets backup job so a
future restore can adapt an older sheet to the current database schema:

- `backup_jobs.backup_schema_version` — bumped whenever a destructive schema
  change alters the shape of the backed-up data.
- `backup_jobs.app_version` — the running application version.
- `backup_jobs.database_revision` — the Alembic revision at backup time.

Non-destructive: only adds nullable/defaulted columns.

Revision ID: 0041_add_backup_schema_version
Revises: 0040_google_sheets_backup
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_add_backup_schema_version"
down_revision = "0040_google_sheets_backup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backup_jobs",
        sa.Column(
            "backup_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column("backup_jobs", sa.Column("app_version", sa.String(50), nullable=True))
    op.add_column("backup_jobs", sa.Column("database_revision", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("backup_jobs", "database_revision")
    op.drop_column("backup_jobs", "app_version")
    op.drop_column("backup_jobs", "backup_schema_version")
