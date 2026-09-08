from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_current_user, get_db_session, list_params, require_permission
from app.modules.administration.schemas import (
    AdminUserOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    SequenceOut,
    SequenceUpdate,
    SettingsOut,
    SettingsPatch,
    UserCreate,
    UserPasswordReset,
    UserUpdate,
)
from app.modules.administration.service import AdministrationService
from app.modules.auth.models import User

router = APIRouter(prefix="/admin", tags=["administration"])


def _user_out(user: User) -> AdminUserOut:
    data = AdminUserOut.model_validate(user)
    data.role = user.role_ref.name if user.role_ref else None
    return data


# ------------------------------------------------------------------- users


@router.get("/users")
async def list_users(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("user.manage")),
) -> dict:
    service = AdministrationService(db)
    users, total = await service.list_users(q=params.q, status=params.status, page=params.page, limit=params.limit)
    return envelope([_user_out(u) for u in users], {"page": params.page, "limit": params.limit, "total": total})


@router.post("/users", status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("user.manage")),
) -> dict:
    service = AdministrationService(db)
    user = await service.create_user(payload, actor=actor)
    return envelope(_user_out(user))


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("user.manage")),
) -> dict:
    service = AdministrationService(db)
    user = await service.update_user(user_id, payload, actor=actor)
    return envelope(_user_out(user))


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    payload: UserPasswordReset,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("user.manage")),
) -> dict:
    service = AdministrationService(db)
    await service.reset_user_password(user_id, payload.new_password, actor=actor)
    return envelope({"message": "Password has been reset"})


# ------------------------------------------------------------------- roles


@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("role.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope([RoleOut.model_validate(r) for r in await service.list_roles()])


@router.post("/roles", status_code=201)
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("role.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope(RoleOut.model_validate(await service.create_role(payload, actor=actor)))


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("role.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope(RoleOut.model_validate(await service.update_role(role_id, payload, actor=actor)))


@router.get("/permissions")
async def get_permissions(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("role.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope(await service.permission_catalog())


# -------------------------------------------------------------- sequences


@router.get("/document-sequences")
async def list_sequences(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("sequence.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope([SequenceOut.model_validate(s) for s in await service.list_sequences()])


@router.patch("/document-sequences/{sequence_id}")
async def update_sequence(
    sequence_id: UUID,
    payload: SequenceUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("sequence.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope(SequenceOut.model_validate(await service.update_sequence(sequence_id, payload)))


# ------------------------------------------------------------- audit logs


@router.get("/audit-logs")
async def list_audit_logs(
    params: ListParams = Depends(list_params),
    user_id: UUID | None = Query(default=None),
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("audit.view")),
) -> dict:
    service = AdministrationService(db)
    logs, total = await service.list_audit_logs(
        q=params.q,
        user_id=user_id,
        module=module,
        action=action,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    from app.shared.pagination.params import list_meta

    data = [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "module": log.module,
            "entity_type": log.entity_type,
            "entity_id": str(log.entity_id) if log.entity_id else None,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
    return envelope(data, list_meta(params.page, params.limit, total))


# --------------------------------------------------------------- settings


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.manage")),
) -> dict:
    service = AdministrationService(db)
    return envelope(SettingsOut(groups=await service.get_settings()))


@router.patch("/settings")
async def update_settings(
    payload: SettingsPatch,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.manage")),
) -> dict:
    service = AdministrationService(db)
    groups = await service.update_settings(payload.values, actor=actor)
    return envelope(SettingsOut(groups=groups))
