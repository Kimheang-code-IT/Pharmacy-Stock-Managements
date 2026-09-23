"""SPA Settings surface (`/api/v1/settings/*`).

Reads project the grouped system settings onto the SPA App Info / App Config
documents; writes delegate to the Administration settings service so auditing,
secret masking and validation rules are unchanged.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import envelope, get_current_user, get_db_session, require_permission
from app.core.config import settings as app_settings
from app.modules.administration import settings_service
from app.modules.administration.maintenance import MaintenanceService, confirmation_phrase
from app.modules.administration.schemas import (
    DestructiveActionRequest,
    MaintenanceReauthRequest,
    MaintenanceReauthResponse,
)
from app.modules.administration.service import AdministrationService
from app.modules.auth.models import User

router = APIRouter(prefix="/settings", tags=["settings"])


def _telegram_status(result: dict) -> dict:
    if not result.get("enabled"):
        return {"status": "disabled", "message": "Telegram notifications are disabled."}
    if not result.get("recipients"):
        return {"status": "failed", "message": "No verified Telegram recipients are linked."}
    if not result.get("sent"):
        return {"status": "failed", "message": "Telegram delivery failed for every recipient."}
    return {
        "status": "connected",
        "message": f"Test message delivered to {result['sent']} recipient(s).",
    }


# ------------------------------------------------------------------ App Config


@router.get("/app-config")
async def get_app_config(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    groups = await AdministrationService(db).get_settings()
    return envelope(
        settings_service.build_app_config(
            groups,
            environment=app_settings.environment,
            environment_token_configured=bool(app_settings.telegram_bot_token),
        )
    )


@router.patch("/app-config")
async def update_app_config(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    service = AdministrationService(db)
    groups = settings_service.app_config_to_groups(payload)
    if groups:
        await service.update_settings(groups, actor=actor)
    return envelope(
        settings_service.build_app_config(
            await service.get_settings(),
            environment=app_settings.environment,
            environment_token_configured=bool(app_settings.telegram_bot_token),
        )
    )


@router.post("/app-config/email/test-connection")
async def test_email_connection(
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    return envelope({"status": "disabled", "message": "Email delivery is not configured on this server."})


@router.post("/app-config/email/send-test")
async def send_test_email(
    payload: dict | None = None,
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    return envelope({"status": "disabled", "message": "Email delivery is not configured on this server."})


@router.post("/app-config/telegram/test-connection")
async def test_telegram_connection(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    from app.shared.telegram.service import send_test_notification

    return envelope(_telegram_status(await send_test_notification(db)))


@router.post("/app-config/telegram/send-test")
async def send_test_telegram(
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    from app.shared.telegram.client import send_message
    from app.shared.telegram.service import send_test_notification

    destination = str((payload or {}).get("destinationId") or "").strip()
    if destination:
        ok = await send_message(
            destination,
            "Stock & POS \u2014 test notification\nTelegram notifications are configured correctly.",
        )
        return envelope(
            {
                "status": "connected" if ok else "failed",
                "message": "Test message sent." if ok else "Telegram rejected the message.",
            }
        )
    return envelope(_telegram_status(await send_test_notification(db)))


# -------------------------------------------------------------------- App Info


@router.get("/app-info")
async def get_app_info(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    return envelope(await settings_service.get_app_info(AdministrationService(db)))


@router.patch("/app-info")
async def update_app_info(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    return envelope(await settings_service.update_app_info(AdministrationService(db), payload, actor=actor))


@router.post("/app-info/reset")
async def reset_app_info(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("settings.update")),
) -> dict:
    return envelope(await settings_service.reset_app_info(AdministrationService(db), actor=actor))


# --------------------------------------------------------- Destructive actions


async def _require_destructive_access(
    actor: User = Depends(get_current_user),
) -> User:
    """Reauth is available to holders of either destructive permission."""
    from app.core.exceptions import AccessDeniedError
    from app.core.permissions import user_has_permission

    if not (
        user_has_permission(actor, "system.data_reset")
        or user_has_permission(actor, "system.maintenance")
    ):
        raise AccessDeniedError()
    return actor


@router.post("/maintenance/reauth")
async def maintenance_reauth(
    payload: MaintenanceReauthRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(_require_destructive_access),
) -> dict:
    """Reauthenticate with the account password and mint a one-use token.

    A destructive action additionally requires this token plus the exact
    confirmation phrase. Requires Administrator-level destructive permission.
    """
    service = MaintenanceService(db)
    token, expires_in = await service.issue_confirmation_token(
        actor=actor, action=payload.action, password=payload.password
    )
    return envelope(
        MaintenanceReauthResponse(
            confirmation_token=token,
            expires_in=expires_in,
            phrase=confirmation_phrase(payload.action),
        )
    )


@router.post("/reset-data")
async def reset_all_data(
    payload: DestructiveActionRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.data_reset")),
) -> dict:
    """Delete every business record and re-seed bootstrap defaults.

    Requires reauthentication (confirmation token), the exact phrase, and a
    verified pre-deletion backup; the audit trail and protected system events
    are preserved. The current administrator, roles, settings and the UOM
    catalogue are kept. The walk-in customer is re-created.
    """
    return envelope(
        await settings_service.reset_all_data(
            AdministrationService(db),
            actor=actor,
            confirmation_token=payload.confirmation_token,
            confirmation_phrase=payload.confirmation_phrase,
        )
    )


@router.post("/clear-transactions")
async def clear_transactions(
    payload: DestructiveActionRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("system.maintenance")),
) -> dict:
    """Delete all sales + purchases (movements, returns, debts, payments,
    delivery notes) and zero product stock.

    Requires reauthentication (confirmation token), the exact phrase, and a
    verified pre-deletion backup. Master data and settings remain."""
    return envelope(
        await settings_service.clear_transactions(
            AdministrationService(db),
            actor=actor,
            confirmation_token=payload.confirmation_token,
            confirmation_phrase=payload.confirmation_phrase,
        )
    )
