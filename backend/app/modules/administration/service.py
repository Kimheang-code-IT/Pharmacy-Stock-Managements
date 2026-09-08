import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import (
    ASSIGNABLE_PERMISSIONS,
    SUPER_ADMIN_PERMISSION,
    normalize_role_permissions,
    permission_catalog,
)
from app.modules.administration.models import SystemSetting
from app.modules.administration.repository import RoleRepository, SettingsRepository, UserRepository
from app.modules.auth.models import User
from app.shared.audit.models import AuditLog
from app.shared.audit.service import record_audit
from app.shared.documents.models import DocumentSequence

logger = logging.getLogger("stock_pos.administration")

# Settings catalog: group -> {key: default}. Secrets are masked on read.
SETTING_GROUPS: dict[str, dict[str, object]] = {
    "shop": {"shop_name": "Yoeun Sokhon Pharmacy", "logo": "", "phone": "", "email": "", "address": ""},
    "currency": {"code": "USD", "symbol": "$", "decimal_places": 2},
    "pos": {
        "default_customer": "",
        "allow_discount": True,
        "maximum_discount": 0,
        "allow_negative_stock": False,
        "receipt_footer": "Thank you for your purchase!",
    },
    "stock": {
        "low_stock_level": 5,
        "expiry_alert_1_days": 90,
        "expiry_alert_2_days": 7,
        "track_expiry": False,
    },
    "telegram": {
        "bot_token": "",
        "enable_password_reset": True,
        "verification_code_expiry": 300,
        "max_verification_attempts": 5,
        "stock_inquiry_enabled": True,
        "payment_invoice_notify_enabled": True,
        "expiry_alerts_enabled": True,
    },
    "invoice": {"logo": "", "footer": "", "paper_size": "A4", "auto_print": False},
    "system": {"language": "en", "date_format": "YYYY-MM-DD", "timezone": "UTC"},
}

SECRET_SETTING_KEYS = frozenset({"telegram.bot_token"})
_MASK = "********"


async def get_setting_value(session: AsyncSession, group: str, key: str, default=None):
    """Public cross-module read of a single setting value (no secrets)."""
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == f"{group}.{key}"))
    setting = result.scalar_one_or_none()
    if setting is None:
        return SETTING_GROUPS.get(group, {}).get(key, default)
    return setting.value.get("v", SETTING_GROUPS.get(group, {}).get(key, default))


class AdministrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.settings = SettingsRepository(session)

    # ------------------------------------------------------------------ users

    async def list_users(self, *, q, status, page, limit) -> tuple[list[User], int]:
        return await self.users.list(q=q, status=status, page=page, limit=limit)

    async def create_user(self, payload, *, actor: User) -> User:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("A user with this email already exists")
        role = await self.roles.get(payload.role_id)
        if role is None or role.status != "ACTIVE":
            raise ValidationError("Selected role does not exist or is inactive", field_errors={"role_id": "Invalid role"})

        from app.core.security import hash_password

        user = User(
            full_name=payload.full_name.strip(),
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            telegram_chat_id=payload.telegram_chat_id,
            role_id=role.id,
            status=payload.status,
        )
        self.session.add(user)
        await self.session.flush()
        await record_audit(
            self.session,
            action="user_created",
            module="administration",
            user_id=actor.id,
            entity_type="user",
            entity_id=user.id,
            new_values={"email": user.email, "role": role.name, "status": user.status},
        )
        await self.session.commit()
        return user

    async def update_user(self, user_id: UUID, payload, *, actor: User) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")

        old = {"email": user.email, "role_id": str(user.role_id), "status": user.status}
        changes: dict[str, object] = {}

        if payload.email and payload.email.lower() != user.email:
            if await self.users.get_by_email(payload.email):
                raise ConflictError("A user with this email already exists")
            user.email = payload.email.lower()
            changes["email"] = user.email
        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
            changes["full_name"] = user.full_name
        if payload.telegram_chat_id is not None:
            user.telegram_chat_id = payload.telegram_chat_id
            changes["telegram_chat_id"] = user.telegram_chat_id
        if payload.status is not None and payload.status != user.status:
            if payload.status == "DISABLED" and user.id == actor.id:
                raise ValidationError("You cannot disable your own account")
            if payload.status == "DISABLED" and await self._is_last_active_admin(user):
                raise ConflictError("Cannot disable the last active administrator")
            user.status = payload.status
            changes["status"] = payload.status
        if payload.role_id is not None and payload.role_id != user.role_id:
            role = await self.roles.get(payload.role_id)
            if role is None or role.status != "ACTIVE":
                raise ValidationError("Selected role does not exist or is inactive", field_errors={"role_id": "Invalid role"})
            if user.id == actor.id or await self._is_last_active_admin(user):
                raise ConflictError("Cannot change the role of the last active administrator")
            user.role_id = role.id
            changes["role_id"] = str(role.id)

        if changes:
            await record_audit(
                self.session,
                action="user_updated",
                module="administration",
                user_id=actor.id,
                entity_type="user",
                entity_id=user.id,
                old_values=old,
                new_values=changes,
            )
        await self.session.commit()
        return user

    async def reset_user_password(self, user_id: UUID, new_password: str, *, actor: User) -> None:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        from app.core.security import hash_password

        user.password_hash = hash_password(new_password)
        user.token_version = (user.token_version or 0) + 1
        await self.session.flush()
        await record_audit(
            self.session,
            action="user_password_reset",
            module="administration",
            user_id=actor.id,
            entity_type="user",
            entity_id=user.id,
        )
        await self.session.commit()

    async def _is_last_active_admin(self, user: User) -> bool:
        return (
            (user.role_ref.name == "Administrator" if user.role_ref else False)
            and user.status == "ACTIVE"
            and await self.users.count_administrators_excluding(user.id) == 0
        )

    # ------------------------------------------------------------------ roles

    async def list_roles(self) -> list:
        return await self.roles.list()

    async def create_role(self, payload, *, actor: User):
        if await self.roles.get_by_name(payload.name):
            raise ConflictError("A role with this name already exists")
        try:
            permissions = normalize_role_permissions(payload.permissions, allow_wildcard=True)
        except ValueError as exc:
            raise ValidationError(str(exc), field_errors={"permissions": str(exc)})
        role = await self.roles.create(payload.name.strip(), payload.description, permissions)
        await record_audit(
            self.session,
            action="role_created",
            module="administration",
            user_id=actor.id,
            entity_type="role",
            entity_id=role.id,
            new_values={"name": role.name, "permissions": permissions},
        )
        await self.session.commit()
        return role

    async def update_role(self, role_id: UUID, payload, *, actor: User):
        role = await self.roles.get(role_id)
        if role is None:
            raise NotFoundError("Role not found")

        old = {"name": role.name, "permissions": role.permissions, "status": role.status}
        changes: dict[str, object] = {}

        if payload.name is not None and payload.name != role.name:
            if role.is_system:
                raise ConflictError("System role names cannot be changed")
            if await self.roles.get_by_name(payload.name):
                raise ConflictError("A role with this name already exists")
            role.name = payload.name.strip()
            changes["name"] = role.name
        if payload.description is not None:
            role.description = payload.description
            changes["description"] = role.description
        if payload.status is not None and payload.status != role.status:
            if role.is_system:
                raise ConflictError("System roles cannot be disabled")
            if payload.status == "DISABLED" and await self.roles.count_users_with_role(role.id) > 0:
                raise ConflictError("Cannot disable a role that still has users")
            role.status = payload.status
            changes["status"] = payload.status
        if payload.permissions is not None:
            if role.name == "Administrator" and SUPER_ADMIN_PERMISSION not in payload.permissions:
                raise ConflictError("The Administrator role must keep full access")
            try:
                permissions = normalize_role_permissions(payload.permissions, allow_wildcard=True)
            except ValueError as exc:
                raise ValidationError(str(exc), field_errors={"permissions": str(exc)})
            await self.roles.set_permissions(role, permissions)
            changes["permissions"] = permissions

        if changes:
            await record_audit(
                self.session,
                action="role_updated",
                module="administration",
                user_id=actor.id,
                entity_type="role",
                entity_id=role.id,
                old_values=old,
                new_values=changes,
            )
        await self.session.commit()
        return role

    async def permission_catalog(self) -> list[dict[str, object]]:
        return permission_catalog()

    # -------------------------------------------------------------- sequences

    async def list_sequences(self) -> list[DocumentSequence]:
        result = await self.session.execute(
            select(DocumentSequence).order_by(DocumentSequence.document_type)
        )
        return list(result.scalars().all())

    async def update_sequence(self, sequence_id: UUID, payload) -> DocumentSequence:
        sequence = await self.session.get(DocumentSequence, sequence_id)
        if sequence is None:
            raise NotFoundError("Document sequence not found")
        if payload.prefix is not None:
            sequence.prefix = payload.prefix.strip()
        if payload.next_number is not None:
            sequence.next_number = payload.next_number
        if payload.number_length is not None:
            sequence.number_length = payload.number_length
        if payload.reset_type is not None:
            sequence.reset_type = payload.reset_type
        if payload.status is not None:
            sequence.status = payload.status
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(sequence)
        return sequence

    # ------------------------------------------------------------- audit logs

    async def list_audit_logs(
        self, *, q, user_id, module, action, start, end, page, limit
    ) -> tuple[list[AuditLog], int]:
        from app.shared.pagination.params import parse_date_range

        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(AuditLog.action.ilike(pattern))
            count_stmt = count_stmt.where(AuditLog.action.ilike(pattern))
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
            count_stmt = count_stmt.where(AuditLog.user_id == user_id)
        if module:
            stmt = stmt.where(AuditLog.module == module)
            count_stmt = count_stmt.where(AuditLog.module == module)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        start_at, end_at = parse_date_range(start, end)
        if start_at is not None:
            stmt = stmt.where(AuditLog.created_at >= start_at)
            count_stmt = count_stmt.where(AuditLog.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(AuditLog.created_at <= end_at)
            count_stmt = count_stmt.where(AuditLog.created_at <= end_at)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    # --------------------------------------------------------------- settings

    async def get_settings(self) -> dict[str, dict[str, object]]:
        stored = {setting.key: setting for setting in await self.settings.all()}
        groups: dict[str, dict[str, object]] = {}
        for group, keys in SETTING_GROUPS.items():
            values: dict[str, object] = {}
            for key, default in keys.items():
                full_key = f"{group}.{key}"
                setting = stored.get(full_key)
                if setting is None:
                    values[key] = default
                elif full_key in SECRET_SETTING_KEYS and setting.value.get("v"):
                    values[key] = _MASK
                else:
                    values[key] = setting.value.get("v", default)
            groups[group] = values
        return groups

    async def update_settings(self, groups: dict[str, dict[str, object]], *, actor: User) -> dict[str, dict[str, object]]:
        for group, values in groups.items():
            if group not in SETTING_GROUPS:
                raise ValidationError(f"Unknown settings group '{group}'")
            allowed = set(SETTING_GROUPS[group].keys())
            for key, value in values.items():
                if key not in allowed:
                    raise ValidationError(f"Unknown settings key '{group}.{key}'")
                if value is _MASK or value == _MASK:
                    raise ValidationError(f"Cannot write masked value for '{group}.{key}'")
                full_key = f"{group}.{key}"
                if full_key == "telegram.bot_token" and value:
                    # Secrets stay server-side: the bot token comes from the
                    # TELEGRAM_BOT_TOKEN environment variable, never the DB.
                    raise ValidationError(
                        "The bot token is configured via the TELEGRAM_BOT_TOKEN environment variable",
                        field_errors={"telegram.bot_token": "Managed by environment"},
                    )
                await self.settings.upsert(
                    group,
                    full_key,
                    value,
                    is_secret=full_key in SECRET_SETTING_KEYS,
                    updated_by=actor.id,
                )
        await record_audit(
            self.session,
            action="settings_changed",
            module="administration",
            user_id=actor.id,
            entity_type="settings",
            new_values={"groups": sorted(groups.keys())},
        )
        await self.session.commit()
        return await self.get_settings()
