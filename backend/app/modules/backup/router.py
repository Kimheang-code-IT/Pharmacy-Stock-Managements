"""Google Sheets backup endpoints (`/api/v1/backup/*`).

Reads (settings/history) are available to settings viewers; running a backup,
testing the connection and changing the configuration require `system.backup`.
Restore is a destructive operation and requires `system.restore` plus a
password reauthentication token and the exact confirmation phrase.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import envelope, get_db_session, require_permission
from app.core.exceptions import NotFoundError
from app.modules.administration.maintenance import MaintenanceService, confirmation_phrase
from app.modules.administration.schemas import MaintenanceReauthRequest, MaintenanceReauthResponse
from app.modules.auth.models import User
from app.modules.backup.schemas import BackupRestoreRequest, BackupSettingsUpdate
from app.modules.backup.service import BackupService

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/settings")
async def get_backup_settings(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.view")),
) -> dict:
    return envelope(await BackupService(db).public_settings())


@router.patch("/settings")
async def update_backup_settings(
    payload: BackupSettingsUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.backup")),
) -> dict:
    return envelope(await BackupService(db).update_settings(payload.to_payload(), actor=actor))


@router.post("/test-connection")
async def test_backup_connection(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.backup")),
) -> dict:
    return envelope(await BackupService(db).test_connection())


@router.post("/run")
async def run_backup_now(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.backup")),
) -> dict:
    service = BackupService(db)
    job = await service.run(actor=actor, trigger="manual")
    return envelope(
        {
            "job": await service.job_detail(job.id),
            "settings": await service.public_settings(),
        }
    )


@router.get("/history")
async def backup_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.view")),
) -> dict:
    jobs, total = await BackupService(db).list_history(page=page, limit=limit)
    return envelope(jobs, {"page": page, "limit": limit, "total": total})


@router.get("/history/{job_id}")
async def backup_history_detail(
    job_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.view")),
) -> dict:
    detail = await BackupService(db).job_detail(job_id)
    if detail is None:
        raise NotFoundError("Backup job not found")
    return envelope(detail)


@router.get("/tables")
async def backup_tables(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.view")),
) -> dict:
    return envelope(await BackupService(db).table_states())


@router.post("/reauth")
async def backup_reauth(
    payload: MaintenanceReauthRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.restore")),
) -> dict:
    """Mint a one-use confirmation token for a restore (password verified)."""
    service = MaintenanceService(db)
    token, expires_in = await service.issue_confirmation_token(
        actor=actor, action="RESTORE_DATABASE", password=payload.password
    )
    return envelope(
        MaintenanceReauthResponse(
            confirmation_token=token,
            expires_in=expires_in,
            phrase=confirmation_phrase("RESTORE_DATABASE"),
        )
    )


@router.post("/restore")
async def restore_backup(
    payload: BackupRestoreRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.restore")),
) -> dict:
    """Restore the latest backed-up version of every record into the database."""
    result = await BackupService(db).restore(
        actor=actor,
        confirmation_token=payload.confirmation_token,
        confirmation_phrase=payload.confirmation_phrase,
        tables=payload.tables,
    )
    return envelope(result)
