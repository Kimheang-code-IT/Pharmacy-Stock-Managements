"""Google Sheets backup: run, change detection, dedupe, restore, permissions.

The remote Google calls are replaced by an in-memory `FakeSheetsGateway`, so
these tests exercise the versioning/bookkeeping logic without network access.
"""

import json
import uuid

import pytest
from sqlalchemy import delete, select

from app.modules.administration.maintenance import MaintenanceService
from app.modules.administration.repository import SettingsRepository
from app.modules.auth.models import User
from app.modules.backup.models import (
    BackupJob,
    BackupJobTable,
    BackupRecord,
    BackupTableState,
)
from app.modules.backup.service import (
    BackupService,
    _detect_change,
    cell,
    row_hash,
)
from tests.utils import admin_headers, create_user_with_role, login

SERVICE_ACCOUNT_JSON = json.dumps(
    {
        "type": "service_account",
        "client_email": "backup-bot@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIBfake\n-----END PRIVATE KEY-----\n",
    }
)


class FakeSheetsGateway:
    """Minimal in-memory SheetsGateway for tests."""

    def __init__(self) -> None:
        self.tabs: dict[str, list[list[str]]] = {}

    async def ensure_worksheet(self, title: str, header: list[str]) -> bool:
        if title not in self.tabs:
            self.tabs[title] = [list(header)]
            return True
        if self.tabs[title][0] != header:
            self.tabs[title][0] = list(header)
            return True
        return False

    async def read_rows(self, title: str) -> list[list[str]]:
        return [list(row) for row in self.tabs.get(title, [])]

    async def append_rows(self, title: str, rows: list[list[str]]) -> None:
        self.tabs.setdefault(title, []).extend([list(row) for row in rows])

    async def test_connection(self) -> dict:
        return {"title": "Fake Sheet", "tabs": list(self.tabs)}

    async def list_titles(self) -> list[str]:
        return list(self.tabs)


@pytest.fixture(autouse=True)
async def _clean_backup_tables(db_session):
    for model in (BackupJobTable, BackupJob, BackupRecord, BackupTableState):
        await db_session.execute(delete(model))
    await db_session.commit()
    yield


async def _configure(db_session, *, enabled: bool = True) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert("backup", "backup.enabled", enabled, is_secret=False, updated_by=None)
    await repo.upsert(
        "backup", "backup.sheet_id", "sheet-test-123", is_secret=False, updated_by=None
    )
    await repo.upsert(
        "backup",
        "backup.service_account_json",
        SERVICE_ACCOUNT_JSON,
        is_secret=True,
        updated_by=None,
    )
    await repo.upsert("backup", "backup.auto_retry", False, is_secret=False, updated_by=None)
    await repo.upsert(
        "backup", "backup.frequency_hours", 1, is_secret=False, updated_by=None
    )
    await db_session.commit()


async def _make_category(db_session, code: str, name: str):
    from app.modules.categories.models import Category

    category = Category(code=code, name=name, status="ACTIVE")
    db_session.add(category)
    await db_session.commit()
    return category


# ------------------------------------------------------------------ unit tests


def test_detect_change_ignores_a_new_column():
    record = type("Record", (), {})()
    record.hashed_columns = ["id", "name"]
    record.row_hash = row_hash({"id": "1", "name": "Alpha"}, ["id", "name"])
    record.version = 1

    unchanged, _ = _detect_change(record, {"id": "1", "name": "Alpha", "extra": "x"}, ["id", "name", "extra"])
    assert unchanged is False

    changed, new_hash = _detect_change(record, {"id": "1", "name": "Beta", "extra": "x"}, ["id", "name", "extra"])
    assert changed is True
    assert new_hash != record.row_hash


def test_cell_serialization_is_stable():
    assert cell(None) == ""
    assert cell(True) == "TRUE"
    assert cell(False) == "FALSE"
    assert cell({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    assert cell([1, "x"]) == '[1, "x"]'


@pytest.mark.asyncio
async def test_run_handles_a_new_column(db_session):
    """A schema change updates the header without re-appending untouched rows."""
    from sqlalchemy import text

    await _configure(db_session)
    await db_session.execute(
        text("CREATE TABLE backup_probe (id TEXT PRIMARY KEY, name TEXT)")
    )
    await db_session.execute(text("INSERT INTO backup_probe (id, name) VALUES ('p1', 'Alpha')"))
    await db_session.commit()

    gateway = FakeSheetsGateway()
    service = BackupService(db_session, gateway=gateway)
    try:
        await service.run(trigger="manual")
        assert "note" not in gateway.tabs["backup_probe"][0]

        await db_session.execute(text("ALTER TABLE backup_probe ADD COLUMN note TEXT"))
        await db_session.commit()

        second = await service.run(trigger="manual")
        header = gateway.tabs["backup_probe"][0]
        assert "note" in header
        # The untouched row must not be re-appended just because a column was added.
        rows = [row for row in gateway.tabs["backup_probe"][1:] if row[-1] == "p1"]
        assert len(rows) == 1
        assert second.rows_appended == 0

        await db_session.execute(text("UPDATE backup_probe SET name = 'Beta', note = 'n1'"))
        await db_session.commit()
        await service.run(trigger="manual")
        rows = [row for row in gateway.tabs["backup_probe"][1:] if row[-1] == "p1"]
        assert len(rows) == 2
        latest = max(rows, key=lambda row: int(row[-3]))
        assert latest[header.index("note")] == "n1"
    finally:
        await db_session.rollback()
        await db_session.execute(text("DROP TABLE IF EXISTS backup_probe"))
        await db_session.commit()


# ----------------------------------------------------------- service run tests


@pytest.mark.asyncio
async def test_run_appends_new_records_and_dedupes(db_session):
    await _configure(db_session)
    category = await _make_category(db_session, f"BK-{uuid.uuid4().hex[:6]}", "Backup Cat")
    gateway = FakeSheetsGateway()

    service = BackupService(db_session, gateway=gateway)
    first = await service.run(trigger="manual")
    assert first.status == "success", first.error_message
    assert first.rows_appended >= 1

    tab = gateway.tabs["categories"]
    header = tab[0]
    assert {"id", "code", "name"} <= set(header)
    assert header[-4:] == ["_backup_date", "_backup_version", "_table_name", "_record_id"]
    rows = [row for row in tab[1:] if row[-1] == str(category.id)]
    assert len(rows) == 1
    assert rows[0][-3] == "1"
    assert rows[0][-2] == "categories"

    # Second run: nothing changed -> no duplicate rows for the category.
    second = await service.run(trigger="manual")
    assert second.rows_appended == 0
    assert second.rows_skipped >= 1
    rows = [row for row in gateway.tabs["categories"][1:] if row[-1] == str(category.id)]
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_run_appends_new_version_on_update(db_session):
    await _configure(db_session)
    category = await _make_category(db_session, f"BK-{uuid.uuid4().hex[:6]}", "Before")
    gateway = FakeSheetsGateway()
    service = BackupService(db_session, gateway=gateway)
    await service.run(trigger="manual")

    category.name = "After"
    await db_session.commit()

    result = await service.run(trigger="manual")
    assert result.rows_updated >= 1

    rows = [row for row in gateway.tabs["categories"][1:] if row[-1] == str(category.id)]
    assert len(rows) == 2
    versions = sorted(row[-3] for row in rows)
    assert versions == ["1", "2"]

    record = (
        await db_session.execute(
            select(BackupRecord).where(BackupRecord.record_id == str(category.id))
        )
    ).scalar_one()
    assert record.version == 2


# ------------------------------------------------------------------- restore


@pytest.mark.asyncio
async def test_restore_reinserts_deleted_rows(db_session):
    await _configure(db_session)
    category = await _make_category(db_session, f"BK-{uuid.uuid4().hex[:6]}", "Restore Me")
    gateway = FakeSheetsGateway()
    service = BackupService(db_session, gateway=gateway)
    await service.run(trigger="manual")

    category_id = category.id
    await db_session.delete(category)
    await db_session.commit()
    assert (
        await db_session.get(type(category), category_id)
    ) is None

    admin = (
        await db_session.execute(select(User).where(User.email == "admin@gmail.com"))
    ).scalar_one()
    token, _ = await MaintenanceService(db_session).issue_confirmation_token(
        actor=admin, action="RESTORE_DATABASE", password="123456"
    )

    restored = await service.restore(
        actor=admin,
        confirmation_token=token,
        confirmation_phrase="RESTORE DATABASE",
        tables=["categories"],
    )
    assert restored["restored"].get("categories", 0) >= 1
    assert (await db_session.get(type(category), category_id)) is not None


@pytest.mark.asyncio
async def test_restore_requires_confirmation(db_session):
    await _configure(db_session)
    admin = (
        await db_session.execute(select(User).where(User.email == "admin@gmail.com"))
    ).scalar_one()
    service = BackupService(db_session, gateway=FakeSheetsGateway())
    with pytest.raises(Exception):
        await service.restore(
            actor=admin,
            confirmation_token=None,
            confirmation_phrase="nope",
            tables=["categories"],
        )


# -------------------------------------------------------------- API surface


@pytest.mark.asyncio
async def test_backup_settings_roundtrip_masks_secret(client):
    admin = await admin_headers(client)
    updated = await client.patch(
        "/api/v1/backup/settings",
        json={
            "enabled": True,
            "sheetId": "sheet-api-1",
            "serviceAccountJson": SERVICE_ACCOUNT_JSON,
            "frequencyHours": 6,
            "backupNewRecords": True,
            "backupChangedRecords": True,
            "autoRetry": True,
            "telegramNotify": False,
        },
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["sheetId"] == "sheet-api-1"
    assert data["frequencyHours"] == 6
    assert data["serviceAccountConfigured"] is True
    assert data["serviceAccountJson"] == "********"
    assert data["telegramNotify"] is False
    assert data["configured"] is True

    fetched = await client.get("/api/v1/backup/settings", headers=admin)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["sheetId"] == "sheet-api-1"


@pytest.mark.asyncio
async def test_backup_rejects_invalid_frequency(client):
    admin = await admin_headers(client)
    response = await client.patch(
        "/api/v1/backup/settings", json={"frequencyHours": 5}, headers=admin
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_backup_run_and_test_connection(client, monkeypatch):
    admin = await admin_headers(client)
    gateway = FakeSheetsGateway()

    monkeypatch.setattr(
        BackupService, "_build_gateway", lambda self, config: gateway
    )

    test = await client.post("/api/v1/backup/test-connection", headers=admin)
    assert test.status_code == 200, test.text
    assert test.json()["data"]["status"] == "connected"

    run = await client.post("/api/v1/backup/run", headers=admin)
    assert run.status_code == 200, run.text
    job = run.json()["data"]["job"]
    assert job["status"] == "success"
    assert job["tablesTotal"] > 0

    history = await client.get("/api/v1/backup/history", headers=admin)
    assert history.status_code == 200
    assert history.json()["meta"]["total"] >= 1


@pytest.mark.asyncio
async def test_backup_permissions(client, db_session):
    email = f"backup-viewer-{uuid.uuid4().hex[:8]}@example.com"
    await create_user_with_role(
        db_session,
        email=email,
        password="BackupViewer1",
        role_name=f"Backup Viewer {uuid.uuid4().hex[:6]}",
        permissions=["settings.view"],
    )
    await db_session.commit()
    data = await login(client, email, "BackupViewer1")
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    assert (await client.get("/api/v1/backup/settings", headers=headers)).status_code == 200
    assert (
        await client.patch("/api/v1/backup/settings", json={"enabled": True}, headers=headers)
    ).status_code == 403
    assert (await client.post("/api/v1/backup/run", headers=headers)).status_code == 403
    assert (
        await client.post("/api/v1/backup/test-connection", headers=headers)
    ).status_code == 403
