from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.backup.models import (
    BackupJob,
    BackupJobTable,
    BackupRecord,
    BackupTableState,
)


class BackupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ jobs

    async def create_job(self, *, trigger: str, created_by: UUID | None) -> BackupJob:
        job = BackupJob(trigger=trigger, created_by=created_by)
        self.session.add(job)
        await self.session.flush()
        return job

    async def add_job_table(self, **values) -> BackupJobTable:
        row = BackupJobTable(**values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_jobs(self, *, page: int, limit: int) -> tuple[list[BackupJob], int]:
        total = int(
            (await self.session.execute(select(func.count()).select_from(BackupJob))).scalar_one()
        )
        rows = await self.session.execute(
            select(BackupJob)
            .order_by(BackupJob.started_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_job(self, job_id: UUID) -> BackupJob | None:
        return await self.session.get(BackupJob, job_id)

    async def job_tables(self, job_id: UUID) -> list[BackupJobTable]:
        rows = await self.session.execute(
            select(BackupJobTable)
            .where(BackupJobTable.job_id == job_id)
            .order_by(BackupJobTable.table_name)
        )
        return list(rows.scalars().all())

    async def latest_jobs(self, limit: int = 1) -> list[BackupJob]:
        rows = await self.session.execute(
            select(BackupJob).order_by(BackupJob.started_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    # --------------------------------------------------------------- records

    async def records_for_table(self, table_name: str) -> dict[str, BackupRecord]:
        rows = await self.session.execute(
            select(BackupRecord).where(BackupRecord.table_name == table_name)
        )
        return {record.record_id: record for record in rows.scalars().all()}

    async def upsert_record(
        self,
        *,
        table_name: str,
        record_id: str,
        version: int,
        row_hash: str,
        hashed_columns: list[str],
        now: datetime,
    ) -> BackupRecord:
        existing = (
            await self.session.execute(
                select(BackupRecord).where(
                    BackupRecord.table_name == table_name,
                    BackupRecord.record_id == record_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = BackupRecord(
                table_name=table_name,
                record_id=record_id,
                version=version,
                row_hash=row_hash,
                hashed_columns=hashed_columns,
                first_backed_up_at=now,
                last_backed_up_at=now,
            )
            self.session.add(existing)
        else:
            existing.version = version
            existing.row_hash = row_hash
            existing.hashed_columns = hashed_columns
            existing.last_backed_up_at = now
        await self.session.flush()
        return existing

    # ---------------------------------------------------------- table states

    async def table_state(self, table_name: str) -> BackupTableState | None:
        return await self.session.get(BackupTableState, table_name)

    async def upsert_table_state(
        self,
        *,
        table_name: str,
        columns: list[str],
        now: datetime,
        row_count: int,
        header_changed: bool,
    ) -> BackupTableState:
        state = await self.session.get(BackupTableState, table_name)
        if state is None:
            state = BackupTableState(
                table_name=table_name,
                columns=columns,
                header_version=1,
                last_backup_at=now,
                last_row_count=row_count,
            )
            self.session.add(state)
        else:
            if header_changed or list(state.columns or []) != list(columns):
                state.header_version = int(state.header_version or 1) + 1
            state.columns = columns
            state.last_backup_at = now
            state.last_row_count = row_count
        await self.session.flush()
        return state

    # ------------------------------------------------------------- retention

    async def delete_records_for_tables(self, table_names: list[str]) -> int:
        if not table_names:
            return 0
        result = await self.session.execute(
            delete(BackupRecord).where(BackupRecord.table_name.in_(table_names))
        )
        return int(result.rowcount or 0)
