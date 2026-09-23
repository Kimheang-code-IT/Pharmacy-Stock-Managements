"""Google Sheets backup bookkeeping.

The Sheets themselves are the append-only data store; these tables only track
what has already been sent so a run can detect new/changed rows and never
re-append a version it already wrote.

- `BackupJob` / `BackupJobTable` — one row per run and per table, so the
  Settings UI can show a backup history with success/failure details.
- `BackupRecord` — the latest backed-up version + hash of one source row,
  keyed by (table_name, record_id). Drives change detection and dedupe.
- `BackupTableState` — the column set last written for a table, so a future
  schema change (new column) is detected and the header is updated.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Status vocabulary shared by jobs and per-table results.
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default=TRIGGER_MANUAL)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_RUNNING)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tables_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tables_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tables_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_appended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_backup_jobs_started_at", "started_at"),)


class BackupJobTable(Base):
    __tablename__ = "backup_job_tables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("backup_jobs.id", ondelete="CASCADE"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_SUCCESS)
    rows_appended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_backup_job_tables_job_id", "job_id"),)


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    record_id: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Columns that produced `row_hash`; a later added column must not look like
    # a change to an otherwise untouched row.
    hashed_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    first_backed_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_backed_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("table_name", "record_id", name="uq_backup_records_table_record"),
        Index("ix_backup_records_table_name", "table_name"),
    )


class BackupTableState(Base):
    __tablename__ = "backup_table_states"

    table_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    header_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
