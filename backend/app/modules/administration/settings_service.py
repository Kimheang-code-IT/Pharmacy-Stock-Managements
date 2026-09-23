"""SPA Settings projections over the grouped system settings catalogue.

The SPA reads two documents — App Info (`shop` identity/branding) and App Config
(general/localization/email/telegram/stock/notifications/security/system) — but
the backend persists a small grouped catalogue (`SETTING_GROUPS`). This module
assembles the SPA shapes from the catalogue and maps writes back onto the
approved groups so auditing, masking and the secret rules stay unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, update

from app.modules.administration.maintenance import MaintenanceService
from app.modules.administration.service import SETTING_GROUPS, AdministrationService
from app.modules.brands.models import Brand
from app.modules.categories.models import Category
from app.modules.customers.models import Customer, CustomerDebt
from app.modules.delivery.models import DeliveryNote, DeliveryNoteItem, DeliveryNoteSale
from app.modules.pos.models import (
    Payment,
    Sale,
    SaleItem,
    SaleItemBatch,
    SaleReturn,
    SaleReturnItem,
)
from app.modules.reports.models import Expense
from app.modules.stock.models import (
    BatchStockBalance,
    Product,
    PurchaseReturn,
    PurchaseReturnItem,
    StockBalance,
    StockMovement,
    StockTransaction,
    StockTransactionItem,
)
from app.modules.suppliers.models import Supplier, SupplierDebt
from app.modules.telegram.models import TelegramExpiryAlertState
from app.modules.uoms.models import UOM
from app.shared.audit.service import record_audit, record_system_event
from app.shared.documents import (
    DocumentSequence,
    allocate_document_number,
    ensure_default_sequences,
)

_MASK = "********"
_DEFAULT_SHOP_NAME = "Yoeun Sokhon Pharmacy"

# Delete order: children before parents so foreign keys never block the wipe.
# Delivery note lines reference sale items (RESTRICT), so delivery tables go
# before SaleItem/Sale.
_CLEAR_TRANSACTION_MODELS: tuple = (
    SaleItemBatch,
    SaleReturnItem,
    SaleReturn,
    DeliveryNoteItem,
    DeliveryNoteSale,
    DeliveryNote,
    Payment,
    CustomerDebt,
    SupplierDebt,
    SaleItem,
    Sale,
    PurchaseReturnItem,
    PurchaseReturn,
    StockMovement,
    StockTransactionItem,
    StockTransaction,
    BatchStockBalance,
)
# Full reset additionally removes master data (AuditLog is intentionally NOT
# deleted: the protected system_audit_events store plus the live audit trail
# must survive a reset so the initiator can never be erased).
_RESET_MODELS: tuple = _CLEAR_TRANSACTION_MODELS + (
    TelegramExpiryAlertState,
    Expense,
    Product,
    Customer,
    Supplier,
    Category,
    Brand,
    UOM,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


# --------------------------------------------------------------- App Info


def build_app_info(groups: dict[str, dict[str, object]]) -> dict:
    shop = groups.get("shop", {})
    name = _str(shop.get("shop_name"), _DEFAULT_SHOP_NAME) or _DEFAULT_SHOP_NAME
    logo = _str(shop.get("logo"))
    branding: dict[str, Any] = {"primaryColor": "#057351", "secondaryColor": "#1f2937"}
    if logo:
        branding["mainLogoUrl"] = logo
    return {
        "applicationName": name,
        "shortName": name,
        "businessName": name,
        "description": "",
        "supportEmail": _str(shop.get("email")),
        "supportPhone": _str(shop.get("phone")),
        "website": "",
        "address": _str(shop.get("address")),
        "branding": branding,
        "footer": {"copyrightText": f"\u00a9 {name}. All rights reserved."},
        "updatedAt": _now(),
    }


async def get_app_info(service: AdministrationService) -> dict:
    return build_app_info(await service.get_settings())


async def update_app_info(
    service: AdministrationService, payload: dict, *, actor: Any
) -> dict:
    shop: dict[str, object] = {}
    field_map = {
        "applicationName": "shop_name",
        "businessName": "shop_name",
        "shortName": "shop_name",
        "supportEmail": "email",
        "supportPhone": "phone",
        "address": "address",
    }
    for source, target in field_map.items():
        value = payload.get(source)
        if isinstance(value, str):
            shop[target] = value
    branding = payload.get("branding")
    if isinstance(branding, dict) and "mainLogoUrl" in branding:
        shop["logo"] = _str(branding.get("mainLogoUrl"))
    if shop:
        await service.update_settings({"shop": shop}, actor=actor)
    return build_app_info(await service.get_settings())


async def reset_app_info(service: AdministrationService, *, actor: Any) -> dict:
    defaults = {key: value for key, value in SETTING_GROUPS["shop"].items()}
    await service.update_settings({"shop": defaults}, actor=actor)
    return build_app_info(await service.get_settings())


async def clear_transactions(
    service: AdministrationService,
    *,
    actor: Any,
    confirmation_token: str | None = None,
    confirmation_phrase: str | None = None,
) -> dict:
    """Delete all sale + purchase history and zero every product's stock.

    Guarded by reauthentication, a one-use confirmation token, an exact phrase
    and a verified pre-deletion backup. Master data (products, customers,
    suppliers, categories, settings) and document sequences are kept, as is the
    audit trail and the protected system-event store.
    """
    session = service.session
    maintenance = MaintenanceService(session)
    await maintenance.consume_confirmation(
        actor=actor,
        action="CLEAR_TRANSACTIONS",
        token=confirmation_token,
        phrase=confirmation_phrase,
    )
    backup = await maintenance.create_backup(
        action="CLEAR_TRANSACTIONS", models=_CLEAR_TRANSACTION_MODELS, actor=actor
    )
    # Evidence of intent, committed BEFORE any deletion.
    await record_system_event(
        session,
        action="transactions_cleared",
        module="administration",
        actor=actor,
        entity_type="system",
        new_values={"phase": "before", "scope": "sales_purchases", "backup": backup["filename"]},
    )
    await session.commit()

    for model in _CLEAR_TRANSACTION_MODELS:
        await session.execute(delete(model))
    # Every movement is gone — reset the materialized balances to zero.
    await session.execute(update(StockBalance).values(quantity=0, average_cost=0))
    await record_audit(
        session,
        action="transactions_cleared",
        module="administration",
        user_id=actor.id,
        entity_type="system",
        entity_id=actor.id,
        new_values={"scope": "sales_purchases", "backup": backup["filename"]},
    )
    await record_system_event(
        session,
        action="transactions_cleared",
        module="administration",
        actor=actor,
        entity_type="system",
        new_values={"phase": "after", "scope": "sales_purchases", "backup": backup["filename"]},
    )
    await session.commit()
    return {
        "cleared": True,
        "requiresReauth": True,
        "backup": backup,
        "message": "Sales and purchase transactions cleared",
    }


async def reset_all_data(
    service: AdministrationService,
    *,
    actor: Any,
    confirmation_token: str | None = None,
    confirmation_phrase: str | None = None,
) -> dict:
    """Wipe every business record and re-seed the bootstrap defaults.

    Guarded by reauthentication, a one-use confirmation token, an exact phrase
    and a verified pre-deletion backup. The audit trail and the protected
    system-event store are preserved so the initiator's evidence survives the
    reset. The current administrator, roles/permissions, system settings and the
    unit-of-measure catalogue are kept so the app stays usable; the walk-in
    customer is re-created for POS.
    """
    session = service.session
    maintenance = MaintenanceService(session)
    await maintenance.consume_confirmation(
        actor=actor,
        action="RESET_ALL_DATA",
        token=confirmation_token,
        phrase=confirmation_phrase,
    )
    backup = await maintenance.create_backup(
        action="RESET_ALL_DATA", models=_RESET_MODELS, actor=actor
    )
    await record_system_event(
        session,
        action="all_data_reset",
        module="administration",
        actor=actor,
        entity_type="system",
        new_values={"phase": "before", "scope": "all_business_data", "backup": backup["filename"]},
    )
    await session.commit()

    for model in _RESET_MODELS:
        await session.execute(delete(model))

    # Reset the document counters, then re-seed the bootstrap rows so the
    # app is immediately usable again.
    await session.execute(update(DocumentSequence).values(next_number=1))
    await ensure_default_sequences(session)
    session.add(
        Customer(
            code=await allocate_document_number(session, "CUSTOMER"),
            name="Walk-in Customer",
            status="ACTIVE",
            is_walk_in=True,
        )
    )
    await session.flush()
    await record_audit(
        session,
        action="all_data_reset",
        module="administration",
        user_id=actor.id,
        entity_type="system",
        entity_id=actor.id,
        new_values={"scope": "all_business_data", "backup": backup["filename"]},
    )
    await record_system_event(
        session,
        action="all_data_reset",
        module="administration",
        actor=actor,
        entity_type="system",
        new_values={"phase": "after", "scope": "all_business_data", "backup": backup["filename"]},
    )
    await session.commit()
    return {
        "message": "All business data has been reset",
        "requiresReauth": True,
        "backup": backup,
    }


# ------------------------------------------------------------- App Config


def _localization(groups: dict[str, dict[str, object]]) -> dict:
    system = groups.get("system", {})
    currency = groups.get("currency", {})
    return {
        "defaultLanguage": "km" if _str(system.get("language"), "en") == "km" else "en",
        "availableLanguages": ["en", "km"],
        "timezone": _str(system.get("timezone"), "Asia/Phnom_Penh") or "Asia/Phnom_Penh",
        "dateFormat": _str(system.get("date_format"), "YYYY-MM-DD") or "YYYY-MM-DD",
        "timeFormat": _str(system.get("time_format"), "HH:mm") or "HH:mm",
        "firstDayOfWeek": _int(system.get("first_day_of_week"), 1),
        "numberFormat": _str(system.get("number_format"), "1,234.56") or "1,234.56",
        "currency": _str(currency.get("code"), "USD") or "USD",
        "locale": _str(system.get("display_locale"), "en-US") or "en-US",
    }


def _telegram(
    groups: dict[str, dict[str, object]], *, shop_name: str, environment_token_configured: bool
) -> dict:
    telegram = groups.get("telegram", {})
    language = _str(telegram.get("notification_language"), "en")
    token_configured = bool(_str(telegram.get("bot_token"))) or environment_token_configured
    return {
        "enabled": _bool(telegram.get("enabled")),
        "botDisplayName": shop_name,
        "botToken": _MASK if token_configured else "",
        "chatId": _str(telegram.get("chat_id")),
        "messageLanguage": "km" if language == "km" else "en",
        "passwordResetEnabled": _bool(telegram.get("enable_password_reset")),
        "paymentInvoiceNotifyEnabled": _bool(telegram.get("payment_invoice_notify_enabled")),
        "stockInquiryEnabled": _bool(telegram.get("stock_inquiry_enabled")),
        "expiryAlertsEnabled": _bool(telegram.get("expiry_alerts_enabled")),
        "saleNotificationsEnabled": _bool(telegram.get("sale_enabled")),
        "purchaseNotificationsEnabled": _bool(telegram.get("purchase_enabled")),
        "dailySummaryEnabled": _bool(telegram.get("daily_summary_enabled")),
        "dailySummaryTime": _str(telegram.get("daily_summary_time"), "07:00") or "07:00",
        "connectionStatus": "disabled",
    }


def _stock(groups: dict[str, dict[str, object]]) -> dict:
    stock = groups.get("stock", {})
    telegram = groups.get("telegram", {})
    return {
        "lowStockLevel": _int(stock.get("low_stock_level"), 5),
        "trackExpiry": _bool(stock.get("track_expiry")),
        "expiryAlert1Days": _int(stock.get("expiry_alert_1_days"), 90),
        "expiryAlert2Days": _int(stock.get("expiry_alert_2_days"), 7),
        "telegramExpiryAlertsEnabled": _bool(telegram.get("expiry_alerts_enabled")),
    }


def _security(groups: dict[str, dict[str, object]]) -> dict:
    sec = groups.get("security", {})
    exts = sec.get("allowed_upload_extensions")
    if not isinstance(exts, list) or not exts:
        exts = ["jpg", "jpeg", "png", "webp", "gif"]
    return {
        "sessionTimeoutMinutes": 120,
        "maxLoginAttempts": _int(sec.get("max_login_attempts"), 5),
        "accountLockMinutes": _int(sec.get("account_lock_minutes"), 15),
        "passwordExpiryDays": _int(sec.get("password_expiry_days"), 180),
        "requirePasswordChange": _bool(sec.get("require_password_change")),
        "allowedUploadExtensions": [str(ext) for ext in exts],
        "auditRetentionDays": _int(sec.get("audit_retention_days"), 365),
        "passwordResetChannel": _str(sec.get("password_reset_channel"), "telegram") or "telegram",
        "passwordResetCodeExpiryMinutes": _int(sec.get("password_reset_code_expiry_minutes"), 10),
        "jwtAccessTokenMinutes": 30,
        "jwtRefreshTokenDays": _int(sec.get("jwt_refresh_token_days"), 14),
        "frontendOnly": False,
    }


def build_app_config(
    groups: dict[str, dict[str, object]],
    *,
    environment: str = "development",
    environment_token_configured: bool = False,
) -> dict:
    shop = groups.get("shop", {})
    shop_name = _str(shop.get("shop_name"), _DEFAULT_SHOP_NAME) or _DEFAULT_SHOP_NAME
    env = environment if environment in {"development", "staging", "production"} else "development"
    return {
        "general": {
            "defaultLandingPage": "/",
            "defaultPageSize": 20,
            "defaultRecordView": "table",
            "enableComments": False,
            "enableSharing": False,
            "enableExport": True,
            "maxUploadSizeMb": 10,
        },
        "localization": _localization(groups),
        "email": {
            "enabled": False,
            "smtpHost": "",
            "smtpPort": 587,
            "username": "",
            "password": "",
            "encryption": "tls",
            "fromName": shop_name,
            "fromEmail": "",
            "timeoutSeconds": 15,
            "connectionStatus": "disabled",
        },
        "telegram": _telegram(
            groups,
            shop_name=shop_name,
            environment_token_configured=environment_token_configured,
        ),
        "stock": _stock(groups),
        "notifications": {
            "inAppEnabled": True,
            "emailEnabled": False,
            "telegramEnabled": False,
            "deliveryRetries": 3,
            "quietHoursEnabled": False,
            "language": "en",
            "rules": [],
        },
        "security": _security(groups),
        "system": {
            "maintenanceMode": False,
            "readOnlyMode": False,
            "paginationDefault": 20,
            "configurationVersion": "1.0.0",
            "environment": env,
            "cacheStatus": "healthy",
            "backgroundJobStatus": "unknown",
        },
        "updatedAt": _now(),
    }


def app_config_to_groups(payload: dict) -> dict[str, dict[str, object]]:
    """Map a partial App Config body onto known settings groups (unknown keys dropped)."""
    groups: dict[str, dict[str, object]] = {}

    stock = payload.get("stock")
    if isinstance(stock, dict):
        group: dict[str, object] = {}
        if "lowStockLevel" in stock:
            group["low_stock_level"] = _int(stock.get("lowStockLevel"), 5)
        if "trackExpiry" in stock:
            group["track_expiry"] = _bool(stock.get("trackExpiry"))
        if "expiryAlert1Days" in stock:
            group["expiry_alert_1_days"] = _int(stock.get("expiryAlert1Days"), 90)
        if "expiryAlert2Days" in stock:
            group["expiry_alert_2_days"] = _int(stock.get("expiryAlert2Days"), 7)
        if "telegramExpiryAlertsEnabled" in stock:
            groups.setdefault("telegram", {})["expiry_alerts_enabled"] = _bool(
                stock.get("telegramExpiryAlertsEnabled")
            )
        if group:
            groups["stock"] = group

    telegram = payload.get("telegram")
    if isinstance(telegram, dict):
        group = groups.setdefault("telegram", {})
        if "enabled" in telegram:
            group["enabled"] = _bool(telegram.get("enabled"))
        if "botToken" in telegram:
            token = _str(telegram.get("botToken")).strip()
            if token != _MASK:
                group["bot_token"] = token
        if "chatId" in telegram:
            group["chat_id"] = _str(telegram.get("chatId")).strip()
        if "passwordResetEnabled" in telegram:
            group["enable_password_reset"] = _bool(telegram.get("passwordResetEnabled"))
        if "paymentInvoiceNotifyEnabled" in telegram:
            group["payment_invoice_notify_enabled"] = _bool(
                telegram.get("paymentInvoiceNotifyEnabled")
            )
        if "stockInquiryEnabled" in telegram:
            group["stock_inquiry_enabled"] = _bool(telegram.get("stockInquiryEnabled"))
        if "expiryAlertsEnabled" in telegram:
            group["expiry_alerts_enabled"] = _bool(telegram.get("expiryAlertsEnabled"))
        if "saleNotificationsEnabled" in telegram:
            group["sale_enabled"] = _bool(telegram.get("saleNotificationsEnabled"))
        if "purchaseNotificationsEnabled" in telegram:
            group["purchase_enabled"] = _bool(telegram.get("purchaseNotificationsEnabled"))
        if "dailySummaryEnabled" in telegram:
            group["daily_summary_enabled"] = _bool(telegram.get("dailySummaryEnabled"))
        time_value = telegram.get("dailySummaryTime")
        if isinstance(time_value, str) and time_value.strip():
            group["daily_summary_time"] = time_value.strip()
        language = telegram.get("messageLanguage")
        if language in {"en", "km"}:
            group["notification_language"] = language

    localization = payload.get("localization")
    if isinstance(localization, dict):
        system = groups.setdefault("system", {})
        if localization.get("defaultLanguage") in {"en", "km"}:
            system["language"] = localization["defaultLanguage"]
        timezone_value = localization.get("timezone")
        if isinstance(timezone_value, str) and timezone_value:
            system["timezone"] = timezone_value
        date_format = localization.get("dateFormat")
        if isinstance(date_format, str) and date_format:
            system["date_format"] = date_format
        time_format = localization.get("timeFormat")
        if isinstance(time_format, str) and time_format:
            system["time_format"] = time_format
        if "firstDayOfWeek" in localization:
            system["first_day_of_week"] = _int(localization.get("firstDayOfWeek"), 1)
        number_format = localization.get("numberFormat")
        if isinstance(number_format, str) and number_format:
            system["number_format"] = number_format
        display_locale = localization.get("locale")
        if isinstance(display_locale, str) and display_locale:
            system["display_locale"] = display_locale
        currency = localization.get("currency")
        if isinstance(currency, str) and currency:
            groups.setdefault("currency", {})["code"] = currency

    security = payload.get("security")
    if isinstance(security, dict):
        sec = groups.setdefault("security", {})
        if "maxLoginAttempts" in security:
            sec["max_login_attempts"] = _int(security.get("maxLoginAttempts"), 5)
        if "accountLockMinutes" in security:
            sec["account_lock_minutes"] = _int(security.get("accountLockMinutes"), 15)
        if "passwordExpiryDays" in security:
            sec["password_expiry_days"] = _int(security.get("passwordExpiryDays"), 180)
        if "auditRetentionDays" in security:
            sec["audit_retention_days"] = _int(security.get("auditRetentionDays"), 365)
        if "requirePasswordChange" in security:
            sec["require_password_change"] = _bool(security.get("requirePasswordChange"))
        if "passwordResetChannel" in security:
            sec["password_reset_channel"] = _str(security.get("passwordResetChannel"), "telegram") or "telegram"
        if "passwordResetCodeExpiryMinutes" in security:
            sec["password_reset_code_expiry_minutes"] = _int(
                security.get("passwordResetCodeExpiryMinutes"), 10
            )
        if "jwtRefreshTokenDays" in security:
            sec["jwt_refresh_token_days"] = _int(security.get("jwtRefreshTokenDays"), 14)
        exts = security.get("allowedUploadExtensions")
        if isinstance(exts, list):
            sec["allowed_upload_extensions"] = [
                str(ext).strip().lstrip(".").lower() for ext in exts if str(ext).strip()
            ]
        elif isinstance(exts, str):
            sec["allowed_upload_extensions"] = [
                ext.strip().lstrip(".").lower() for ext in exts.split(",") if ext.strip()
            ]

    return {group: values for group, values in groups.items() if values}
