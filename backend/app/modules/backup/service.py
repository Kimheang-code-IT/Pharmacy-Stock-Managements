"""Automatic Google Sheets backup service.

Every public table (except the backup bookkeeping tables and Alembic's version
table) gets its own tab. The design is append-only and versioned:

- a new source row is appended with `_backup_version = 1`;
- a changed row is appended again with the next version (old versions stay);
- an unchanged row is skipped, so a run never duplicates a record;
- the latest `(record_id, version)` present in the sheet is a second guard that
  keeps a crash between the append and the DB commit from re-writing a version.

`backup_records` stores the hash of the last backed-up row to detect changes;
`backup_table_states` stores the column set so a future schema change (new
column) is detected and the sheet header is updated.

Restore reads the latest version of every record back out of the sheets and
upserts it into PostgreSQL in foreign-key order.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.security import utcnow
from app.modules.administration.maintenance import MaintenanceService
from app.modules.administration.repository import SettingsRepository
from app.modules.administration.service import get_setting_value
from app.modules.backup.models import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    TRIGGER_MANUAL,
    BackupJob,
)
from app.modules.backup.repository import BackupRepository
from app.modules.backup.sheets import GoogleSheetsGateway, SheetsGateway
from app.shared.audit.service import record_system_event

logger = logging.getLogger("stock_pos.backup")

META_COLUMNS = ["_backup_date", "_backup_version", "_table_name", "_record_id"]
BACKUP_DATE_COLUMN = "_backup_date"
BACKUP_VERSION_COLUMN = "_backup_version"
TABLE_NAME_COLUMN = "_table_name"
RECORD_ID_COLUMN = "_record_id"

# Bump this whenever a destructive schema change alters the shape of the data
# written to Google Sheets, so a future restore can adapt an older sheet to the
# current database schema (recorded on every BackupJob).
BACKUP_SCHEMA_VERSION = 1

# In-DB archives created by migration 0042 (legacy_archive_*). They are not
# business data and must never be reflected into a spreadsheet.
ARCHIVE_TABLE_PREFIX = "legacy_archive_"

# The backup bookkeeping tables would recurse; Alembic's version table is not
# business data. `system_settings` is excluded deliberately: it holds secrets
# (the Telegram bot token and the Google service-account key) that must never be
# written into a spreadsheet, and the backup run-state is stored there too.
EXCLUDED_TABLES = frozenset(
    {
        "alembic_version",
        "backup_jobs",
        "backup_job_tables",
        "backup_records",
        "backup_table_states",
        "system_settings",
    }
)

ALLOWED_FREQUENCY_HOURS = (1, 3, 6, 12, 24)
DEFAULT_FREQUENCY_HOURS = 24
INSERT_CHUNK = 500


# --------------------------------------------------------------- serialization


def cell(value: Any) -> str:
    """Render one value as a stable spreadsheet cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


def _token(value: Any) -> str:
    """Type-tagged token so `None`, `""` and `"None"` hash differently."""
    return f"{type(value).__name__}:{cell(value)}"


def row_hash(raw: dict[str, Any], columns: list[str]) -> str:
    payload = "|".join(f"{column}={_token(raw.get(column))}" for column in columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _from_cell(column, raw: Any) -> Any:
    """Best-effort inverse of `cell`, guided by the reflected column type."""
    if raw is None or raw == "":
        return None
    text = str(raw)
    try:
        python_type = column.type.python_type
    except (NotImplementedError, AttributeError):
        python_type = str
    try:
        if python_type is bool:
            return text.strip().lower() in {"true", "1", "yes", "t"}
        if python_type is int:
            return int(Decimal(text))
        if python_type is float:
            return float(text)
        if python_type is Decimal:
            return Decimal(text)
        if python_type is datetime:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        if python_type is date:
            return date.fromisoformat(text)
        if python_type is UUID:
            return UUID(text)
        if python_type is bytes:
            return bytes.fromhex(text)
        if python_type in (dict, list):
            return json.loads(text)
    except (ValueError, TypeError, InvalidOperation, json.JSONDecodeError):
        return text
    if text[:1] in {"{", "["}:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


# --------------------------------------------------------------------- config


@dataclass
class BackupConfig:
    enabled: bool
    sheet_id: str
    service_account_json: str
    frequency_hours: int
    backup_new_records: bool
    backup_changed_records: bool
    auto_retry: bool
    retry_attempts: int
    telegram_notify: bool

    @property
    def configured(self) -> bool:
        return bool(self.sheet_id.strip() and self.service_account_json.strip())


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class BackupService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        gateway: SheetsGateway | None = None,
    ) -> None:
        self.session = session
        self.repo = BackupRepository(session)
        self._gateway = gateway

    # ------------------------------------------------------------------ config

    async def _load_config(self) -> BackupConfig:
        frequency = _coerce_int(
            await get_setting_value(self.session, "backup", "frequency_hours", DEFAULT_FREQUENCY_HOURS),
            DEFAULT_FREQUENCY_HOURS,
        )
        if frequency not in ALLOWED_FREQUENCY_HOURS:
            frequency = DEFAULT_FREQUENCY_HOURS
        return BackupConfig(
            enabled=_coerce_bool(await get_setting_value(self.session, "backup", "enabled", False), False),
            sheet_id=str(await get_setting_value(self.session, "backup", "sheet_id", "") or "").strip(),
            service_account_json=str(
                await get_setting_value(self.session, "backup", "service_account_json", "") or ""
            ),
            frequency_hours=frequency,
            backup_new_records=_coerce_bool(
                await get_setting_value(self.session, "backup", "backup_new_records", True), True
            ),
            backup_changed_records=_coerce_bool(
                await get_setting_value(self.session, "backup", "backup_changed_records", True), True
            ),
            auto_retry=_coerce_bool(await get_setting_value(self.session, "backup", "auto_retry", True), True),
            retry_attempts=max(
                1,
                min(6, _coerce_int(await get_setting_value(self.session, "backup", "retry_attempts", 3), 3)),
            ),
            telegram_notify=_coerce_bool(
                await get_setting_value(self.session, "backup", "telegram_notify", True), True
            ),
        )

    def _build_gateway(self, config: BackupConfig) -> SheetsGateway:
        if self._gateway is not None:
            return self._gateway
        return GoogleSheetsGateway(
            sheet_id=config.sheet_id,
            service_account_json=config.service_account_json,
            auto_retry=config.auto_retry,
            retry_attempts=config.retry_attempts,
        )

    async def public_settings(self) -> dict:
        config = await self._load_config()
        last_success = str(await get_setting_value(self.session, "backup", "last_success_at", "") or "")
        next_run = str(await get_setting_value(self.session, "backup", "next_run_at", "") or "")
        last_status = str(await get_setting_value(self.session, "backup", "last_job_status", "") or "")
        last_error = str(await get_setting_value(self.session, "backup", "last_error", "") or "")
        return {
            "enabled": config.enabled,
            "sheetId": config.sheet_id,
            "serviceAccountConfigured": bool(config.service_account_json.strip()),
            "serviceAccountJson": "********" if config.service_account_json.strip() else "",
            "frequencyHours": config.frequency_hours,
            "frequencyOptions": list(ALLOWED_FREQUENCY_HOURS),
            "backupNewRecords": config.backup_new_records,
            "backupChangedRecords": config.backup_changed_records,
            "autoRetry": config.auto_retry,
            "retryAttempts": config.retry_attempts,
            "telegramNotify": config.telegram_notify,
            "configured": config.configured,
            "lastSuccessAt": last_success or None,
            "nextRunAt": next_run or None,
            "lastJobStatus": last_status or None,
            "lastError": last_error or None,
        }

    async def update_settings(self, payload: dict, *, actor) -> dict:
        from app.modules.administration.service import AdministrationService

        values: dict[str, object] = {}
        if "enabled" in payload:
            values["enabled"] = _coerce_bool(payload.get("enabled"), False)
        if "sheetId" in payload or "sheet_id" in payload:
            sheet_id = str(payload.get("sheetId", payload.get("sheet_id", "")) or "").strip()
            if len(sheet_id) > 200:
                raise ValidationError(
                    "The Google Sheet ID is too long",
                    field_errors={"sheet_id": "Maximum length is 200 characters"},
                )
            values["sheet_id"] = sheet_id
        secret = payload.get("serviceAccountJson", payload.get("service_account_json"))
        if secret is not None:
            secret = str(secret)
            if secret.strip() and secret != "********":
                if not _is_service_account_json(secret):
                    raise ValidationError(
                        "The service account key is not valid JSON",
                        field_errors={"service_account_json": "Paste the service account JSON key"},
                    )
                values["service_account_json"] = secret.strip()
        if "frequencyHours" in payload or "frequency_hours" in payload:
            frequency = _coerce_int(
                payload.get("frequencyHours", payload.get("frequency_hours")), DEFAULT_FREQUENCY_HOURS
            )
            if frequency not in ALLOWED_FREQUENCY_HOURS:
                raise ValidationError(
                    "Unsupported backup frequency",
                    field_errors={"frequency_hours": "Choose 1, 3, 6, 12 or 24 hours"},
                )
            values["frequency_hours"] = frequency
        if "backupNewRecords" in payload:
            values["backup_new_records"] = _coerce_bool(payload.get("backupNewRecords"), True)
        if "backupChangedRecords" in payload:
            values["backup_changed_records"] = _coerce_bool(payload.get("backupChangedRecords"), True)
        if "autoRetry" in payload:
            values["auto_retry"] = _coerce_bool(payload.get("autoRetry"), True)
        if "retryAttempts" in payload:
            values["retry_attempts"] = max(1, min(6, _coerce_int(payload.get("retryAttempts"), 3)))
        if "telegramNotify" in payload:
            values["telegram_notify"] = _coerce_bool(payload.get("telegramNotify"), True)

        if values:
            await AdministrationService(self.session).update_settings({"backup": values}, actor=actor)
        return await self.public_settings()

    # -------------------------------------------------------------- reflection

    async def _reflect_tables(self) -> dict[str, Table]:
        metadata = MetaData()
        connection = await self.session.connection()

        def _reflect(sync_connection):
            inspector = inspect(sync_connection)
            tables: dict[str, Table] = {}
            for name in inspector.get_table_names(schema="public"):
                if name in EXCLUDED_TABLES or name.startswith(ARCHIVE_TABLE_PREFIX):
                    continue
                tables[name] = Table(
                    name, metadata, schema="public", autoload_with=sync_connection
                )
            return tables

        return await connection.run_sync(_reflect)

    async def _database_revision(self) -> str | None:
        """Alembic revision at backup time (metadata only; never fails a run).

        Uses `to_regclass` first so a database without the Alembic table (e.g. a
        test schema built via `create_all`) does not abort the transaction.
        """
        try:
            present = (
                await self.session.execute(
                    text("SELECT to_regclass('public.alembic_version')")
                )
            ).scalar_one_or_none()
            if present is None:
                return None
            result = await self.session.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()
        except Exception:  # noqa: BLE001
            return None

    # -------------------------------------------------------------------- run

    async def run(
        self,
        *,
        actor=None,
        trigger: str = TRIGGER_MANUAL,
        gateway: SheetsGateway | None = None,
    ) -> BackupJob:
        config = await self._load_config()
        gateway = gateway or self._gateway or self._build_gateway(config)

        job = await self.repo.create_job(
            trigger=trigger, created_by=getattr(actor, "id", None)
        )
        job.backup_schema_version = BACKUP_SCHEMA_VERSION
        job.app_version = settings.app_version
        job.database_revision = await self._database_revision()
        # Persist the running job first so the UI can show progress.
        await self.session.commit()

        now = utcnow()
        try:
            tables = await self._reflect_tables()
        except Exception as exc:  # noqa: BLE001 - recorded on the job
            logger.exception("Backup failed to reflect the database schema")
            job.status = STATUS_FAILED
            job.finished_at = utcnow()
            job.error_message = f"Schema reflection failed: {exc}"
            await self._write_run_state(job, config, now)
            await self.session.commit()
            await self._notify(job, config)
            return job

        job.tables_total = len(tables)
        for name in sorted(tables):
            table = tables[name]
            started = time.perf_counter()
            try:
                async with self.session.begin_nested():
                    outcome = await self._backup_table(gateway, table, config, now)
                job.tables_succeeded += 1
                job.rows_appended += outcome["appended"]
                job.rows_updated += outcome["updated"]
                job.rows_skipped += outcome["skipped"]
                await self.repo.add_job_table(
                    job_id=job.id,
                    table_name=name,
                    status=STATUS_SUCCESS,
                    rows_appended=outcome["appended"],
                    rows_updated=outcome["updated"],
                    rows_skipped=outcome["skipped"],
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - one table must not abort the run
                logger.exception("Backup failed for table %s", name)
                job.tables_failed += 1
                job.error_message = f"{name}: {exc}"
                await self.repo.add_job_table(
                    job_id=job.id,
                    table_name=name,
                    status=STATUS_FAILED,
                    error_message=str(exc)[:2000],
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            await self.session.flush()

        job.finished_at = utcnow()
        if job.tables_failed == 0:
            job.status = STATUS_SUCCESS
        elif job.tables_succeeded == 0:
            job.status = STATUS_FAILED
        else:
            job.status = STATUS_PARTIAL
        await self._write_run_state(job, config, now)
        await self.session.commit()
        await self._notify(job, config)
        return job

    async def _backup_table(
        self, gateway: SheetsGateway, table: Table, config: BackupConfig, now: datetime
    ) -> dict:
        table_name = table.name
        columns = [column.name for column in table.columns]
        header = columns + META_COLUMNS

        header_changed = await gateway.ensure_worksheet(table_name, header)
        existing = await gateway.read_rows(table_name)
        existing_versions = _existing_versions(existing)
        records = await self.repo.records_for_table(table_name)

        pk_names = [column.name for column in table.primary_key.columns]
        result = await self.session.execute(select(table))
        rows = result.mappings().all()

        backup_date = now.isoformat()
        append_rows: list[list[str]] = []
        mutations: list[tuple[str, int, str, list[str]]] = []
        appended = updated = skipped = 0

        for row in rows:
            raw = {column.name: row[column.name] for column in table.columns}
            record_id = (
                "|".join(cell(row[name]) for name in pk_names)
                if pk_names
                else row_hash(raw, columns)
            )
            existing_record = records.get(record_id)
            if existing_record is None:
                if not config.backup_new_records:
                    skipped += 1
                    continue
                version = 1
                is_new = True
            else:
                changed, new_hash = _detect_change(existing_record, raw, columns)
                if not changed or not config.backup_changed_records:
                    skipped += 1
                    continue
                version = int(existing_record.version or 1) + 1
                is_new = False

            sheet_version = existing_versions.get(record_id)
            if sheet_version is not None and sheet_version >= version:
                # Already written in a previous attempt (crash after append,
                # before commit). Reconcile the bookkeeping without appending.
                mutations.append((record_id, sheet_version, row_hash(raw, columns), columns))
                skipped += 1
                continue

            append_rows.append(
                [cell(raw[column]) for column in columns]
                + [backup_date, str(version), table_name, record_id]
            )
            mutations.append((record_id, version, row_hash(raw, columns), columns))
            if is_new:
                appended += 1
            else:
                updated += 1

        if append_rows:
            await gateway.append_rows(table_name, append_rows)

        for record_id, version, digest, hashed_columns in mutations:
            await self.repo.upsert_record(
                table_name=table_name,
                record_id=record_id,
                version=version,
                row_hash=digest,
                hashed_columns=hashed_columns,
                now=now,
            )

        await self.repo.upsert_table_state(
            table_name=table_name,
            columns=columns,
            now=now,
            row_count=len(rows),
            header_changed=header_changed,
        )
        return {"appended": appended, "updated": updated, "skipped": skipped}

    async def _write_run_state(self, job: BackupJob, config: BackupConfig, now: datetime) -> None:
        settings = SettingsRepository(self.session)
        next_run = now + timedelta(hours=config.frequency_hours)
        await settings.upsert(
            "backup", "backup.last_job_status", job.status, is_secret=False, updated_by=job.created_by
        )
        await settings.upsert(
            "backup",
            "backup.last_error",
            (job.error_message or "")[:2000],
            is_secret=False,
            updated_by=job.created_by,
        )
        await settings.upsert(
            "backup",
            "backup.next_run_at",
            next_run.isoformat(),
            is_secret=False,
            updated_by=job.created_by,
        )
        if job.status == STATUS_SUCCESS:
            await settings.upsert(
                "backup",
                "backup.last_success_at",
                now.isoformat(),
                is_secret=False,
                updated_by=job.created_by,
            )

    async def _notify(self, job: BackupJob, config: BackupConfig) -> None:
        if not config.telegram_notify:
            return
        try:
            from app.shared.telegram.service import notify_backup_result

            await notify_backup_result(self.session, job=job)
        except Exception:  # noqa: BLE001 - notification never breaks a backup
            logger.exception("Backup Telegram notification failed")

    # ---------------------------------------------------------------- restore

    async def restore(
        self,
        *,
        actor,
        confirmation_token: str | None,
        confirmation_phrase: str | None,
        tables: list[str] | None = None,
        gateway: SheetsGateway | None = None,
    ) -> dict:
        await MaintenanceService(self.session).consume_confirmation(
            actor=actor,
            action="RESTORE_DATABASE",
            token=confirmation_token,
            phrase=confirmation_phrase,
        )
        config = await self._load_config()
        gateway = gateway or self._gateway or self._build_gateway(config)
        if not config.configured:
            raise ValidationError("Google Sheets backup is not configured")

        reflected = await self._reflect_tables()
        selected = set(tables) if tables else None
        if selected is not None:
            reflected = {name: table for name, table in reflected.items() if name in selected}

        await record_system_event(
            self.session,
            action="backup_restore_started",
            module="backup",
            actor=actor,
            entity_type="system",
            new_values={"tables": sorted(reflected)},
        )
        await self.session.commit()

        restored: dict[str, int] = {}
        skipped: list[str] = []
        for name in _order_by_dependencies(reflected):
            table = reflected[name]
            pk_names = [column.name for column in table.primary_key.columns]
            if not pk_names:
                skipped.append(name)
                continue
            rows = await gateway.read_rows(name)
            if len(rows) < 2:
                restored[name] = 0
                continue
            latest = _latest_rows(rows[0], rows[1:])
            if not latest:
                restored[name] = 0
                continue
            count = await self._upsert_rows(table, pk_names, latest)
            await self.session.commit()
            restored[name] = count

        await record_system_event(
            self.session,
            action="backup_restored",
            module="backup",
            actor=actor,
            entity_type="system",
            new_values={"restored": restored, "skipped": skipped},
        )
        await self.session.commit()
        return {
            "restored": restored,
            "skipped": skipped,
            "totalRows": sum(restored.values()),
        }

    async def _upsert_rows(self, table: Table, pk_names: list[str], rows: list[dict]) -> int:
        dialect = self.session.get_bind().dialect.name
        if dialect != "postgresql":
            raise ValidationError("Restore requires a PostgreSQL database")
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        columns = list(table.columns)
        payload = []
        for row in rows:
            payload.append(
                {column.name: _from_cell(column, row.get(column.name)) for column in columns}
            )
        non_pk = [column.name for column in columns if column.name not in pk_names]
        count = 0
        for start in range(0, len(payload), INSERT_CHUNK):
            chunk = payload[start : start + INSERT_CHUNK]
            statement = pg_insert(table).values(chunk)
            if non_pk:
                statement = statement.on_conflict_do_update(
                    index_elements=pk_names,
                    set_={name: statement.excluded[name] for name in non_pk},
                )
            else:
                statement = statement.on_conflict_do_nothing(index_elements=pk_names)
            await self.session.execute(statement)
            count += len(chunk)
        return count

    # ---------------------------------------------------------------- history

    async def test_connection(self) -> dict:
        config = await self._load_config()
        if not config.configured:
            return {"status": "disabled", "message": "Google Sheets backup is not configured yet."}
        gateway = self._gateway or self._build_gateway(config)
        try:
            info = await gateway.test_connection()
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed status
            return {"status": "failed", "message": str(exc)}
        return {
            "status": "connected",
            "message": f"Connected to '{info.get('title', 'spreadsheet')}' ({len(info.get('tabs', []))} tabs).",
            "spreadsheet": info,
        }

    async def list_history(self, *, page: int, limit: int) -> tuple[list[dict], int]:
        jobs, total = await self.repo.list_jobs(page=page, limit=limit)
        return [_job_out(job) for job in jobs], total

    async def job_detail(self, job_id: UUID) -> dict | None:
        job = await self.repo.get_job(job_id)
        if job is None:
            return None
        tables = await self.repo.job_tables(job_id)
        return {
            **_job_out(job),
            "tables": [
                {
                    "tableName": row.table_name,
                    "status": row.status,
                    "rowsAppended": row.rows_appended,
                    "rowsUpdated": row.rows_updated,
                    "rowsSkipped": row.rows_skipped,
                    "durationMs": row.duration_ms,
                    "errorMessage": row.error_message,
                }
                for row in tables
            ],
        }

    async def table_states(self) -> list[dict]:
        from app.modules.backup.models import BackupTableState

        result = await self.session.execute(
            select(BackupTableState).order_by(BackupTableState.table_name)
        )
        return [
            {
                "tableName": state.table_name,
                "columnCount": len(state.columns or []),
                "headerVersion": state.header_version,
                "lastBackupAt": state.last_backup_at.isoformat() if state.last_backup_at else None,
                "lastRowCount": state.last_row_count,
            }
            for state in result.scalars().all()
        ]


# ------------------------------------------------------------------ helpers


def _is_service_account_json(value: str) -> bool:
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("client_email")) and bool(data.get("private_key"))


def _detect_change(existing, raw: dict[str, Any], current_columns: list[str]) -> tuple[bool, str]:
    hashed_columns = list(existing.hashed_columns or [])
    new_hash = row_hash(raw, current_columns)
    if not hashed_columns:
        return True, new_hash
    if any(column not in raw for column in hashed_columns):
        # A hashed column was dropped from the table.
        return True, new_hash
    return row_hash(raw, hashed_columns) != existing.row_hash, new_hash


def _existing_versions(rows: list[list[str]]) -> dict[str, int]:
    """Map `_record_id` -> highest `_backup_version` already present in a tab."""
    if len(rows) < 2:
        return {}
    header = rows[0]
    try:
        record_index = header.index(RECORD_ID_COLUMN)
        version_index = header.index(BACKUP_VERSION_COLUMN)
    except ValueError:
        return {}
    versions: dict[str, int] = {}
    for row in rows[1:]:
        if record_index >= len(row) or version_index >= len(row):
            continue
        record_id = row[record_index]
        if not record_id:
            continue
        try:
            version = int(row[version_index])
        except (TypeError, ValueError):
            continue
        if version > versions.get(record_id, 0):
            versions[record_id] = version
    return versions


def _latest_rows(header: list[str], rows: list[list[str]]) -> list[dict]:
    """Keep only the highest-version row per `_record_id` from a tab."""
    try:
        record_index = header.index(RECORD_ID_COLUMN)
        version_index = header.index(BACKUP_VERSION_COLUMN)
    except ValueError:
        return []
    best: dict[str, tuple[int, dict]] = {}
    for row in rows:
        if record_index >= len(row):
            continue
        record_id = row[record_index]
        if not record_id:
            continue
        try:
            version = int(row[version_index]) if version_index < len(row) else 0
        except (TypeError, ValueError):
            version = 0
        values = {
            column: (row[index] if index < len(row) else "")
            for index, column in enumerate(header)
            if column not in META_COLUMNS
        }
        previous = best.get(record_id)
        if previous is None or version >= previous[0]:
            best[record_id] = (version, values)
    return [values for _, values in best.values()]


def _order_by_dependencies(tables: dict[str, Table]) -> list[str]:
    remaining = dict(tables)
    placed: set[str] = set()
    ordered: list[str] = []
    while remaining:
        progressed = False
        for name in list(remaining):
            dependencies = {
                foreign_key.column.table.name
                for foreign_key in remaining[name].foreign_keys
                if foreign_key.column.table.name in remaining
                and foreign_key.column.table.name != name
            }
            if dependencies <= placed:
                ordered.append(name)
                placed.add(name)
                del remaining[name]
                progressed = True
        if not progressed:
            ordered.extend(remaining.keys())
            break
    return ordered


def _job_out(job: BackupJob) -> dict:
    return {
        "id": str(job.id),
        "trigger": job.trigger,
        "status": job.status,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
        "tablesTotal": job.tables_total,
        "tablesSucceeded": job.tables_succeeded,
        "tablesFailed": job.tables_failed,
        "rowsAppended": job.rows_appended,
        "rowsUpdated": job.rows_updated,
        "rowsSkipped": job.rows_skipped,
        "errorMessage": job.error_message,
        "backupSchemaVersion": job.backup_schema_version,
        "appVersion": job.app_version,
        "databaseRevision": job.database_revision,
        "createdBy": str(job.created_by) if job.created_by else None,
    }
