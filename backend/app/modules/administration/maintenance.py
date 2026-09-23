"""Guarded destructive maintenance operations.

A destructive action (clear transactions, reset all business data) requires ALL
of the following, enforced server-side:

1. an Administrator-level permission (`system.data_reset` / `system.maintenance`);
2. a recent password reauthentication;
3. a short-lived, single-use confirmation token bound to the actor + action;
4. an exact confirmation phrase;
5. a verified backup created immediately before deletion (abort if it fails);
6. protected audit events written before AND after the operation.

The confirmation token lives in Redis and FAILS CLOSED when Redis is
unavailable — a destructive action must never run without it.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    MaintenanceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.redis import get_redis
from app.core.security import utcnow, verify_password

logger = logging.getLogger("stock_pos.maintenance")

CONFIRMATION_PREFIX = "maint:confirm"
CONFIRMATION_TTL_SECONDS = 120

# Exact phrase the operator must type, per action.
CONFIRMATION_PHRASES = {
    "CLEAR_TRANSACTIONS": "CLEAR TRANSACTIONS",
    "RESET_ALL_DATA": "RESET ALL DATA",
    "RESTORE_DATABASE": "RESTORE DATABASE",
}


def confirmation_phrase(action: str) -> str:
    return CONFIRMATION_PHRASES.get(action, "")


class MaintenanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------- reauthentication

    async def issue_confirmation_token(self, *, actor, action: str, password: str) -> tuple[str, int]:
        """Verify the actor's password and mint a one-use confirmation token."""
        action = (action or "").strip().upper()
        if action not in CONFIRMATION_PHRASES:
            raise ValidationError("Unknown maintenance action", field_errors={"action": "Unknown action"})
        if not password or not verify_password(actor.password_hash, password):
            raise ValidationError(
                "Password is incorrect", field_errors={"password": "Incorrect password"}
            )
        token = secrets.token_urlsafe(32)
        client = get_redis()
        try:
            await client.set(
                f"{CONFIRMATION_PREFIX}:{token}",
                json.dumps({"user_id": str(actor.id), "action": action}),
                ex=CONFIRMATION_TTL_SECONDS,
            )
        except Exception as exc:  # fail closed
            logger.error("Confirmation store unavailable: %s", exc)
            raise ServiceUnavailableError(
                "Confirmation is temporarily unavailable. Try again later."
            ) from exc
        return token, CONFIRMATION_TTL_SECONDS

    async def consume_confirmation(self, *, actor, action: str, token: str | None, phrase: str | None) -> None:
        """Validate + consume the one-use token and the exact confirmation phrase."""
        action = (action or "").strip().upper()
        expected_phrase = CONFIRMATION_PHRASES.get(action)
        if expected_phrase is None:
            raise ValidationError("Unknown maintenance action")
        if (phrase or "").strip() != expected_phrase:
            raise ValidationError(
                f'Type "{expected_phrase}" exactly to confirm',
                field_errors={"confirmation_phrase": "Confirmation phrase does not match"},
            )
        if not token:
            raise ValidationError(
                "A confirmation token is required",
                field_errors={"confirmation_token": "Missing confirmation token"},
            )
        client = get_redis()
        key = f"{CONFIRMATION_PREFIX}:{token}"
        try:
            raw = await client.get(key)
        except Exception as exc:  # fail closed
            logger.error("Confirmation store unavailable: %s", exc)
            raise ServiceUnavailableError(
                "Confirmation is temporarily unavailable. Try again later."
            ) from exc
        if not raw:
            raise ValidationError(
                "The confirmation token is invalid or has expired",
                field_errors={"confirmation_token": "Invalid or expired token"},
            )
        data = json.loads(raw)
        if str(data.get("user_id")) != str(actor.id) or data.get("action") != action:
            raise ValidationError(
                "The confirmation token does not match this action",
                field_errors={"confirmation_token": "Token/action mismatch"},
            )
        # Single use: consume it before proceeding.
        try:
            await client.delete(key)
        except Exception as exc:
            logger.error("Failed to consume confirmation token: %s", exc)
            raise ServiceUnavailableError(
                "Confirmation is temporarily unavailable. Try again later."
            ) from exc

    # --------------------------------------------------------------- backups

    @staticmethod
    def _serialize(value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value

    async def create_backup(self, *, action: str, models: tuple, actor) -> dict:
        """Write a verified JSON snapshot of the affected tables.

        Raises MaintenanceError if the snapshot cannot be written or fails the
        integrity check, so the caller MUST abort the deletion.
        """
        # Private backup root — intentionally separate from the public media
        # directory so snapshots can never be downloaded via /api/v1/images.
        backup_dir = Path(settings.backup_dir).expanduser().resolve()
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise MaintenanceError(f"Could not create the backup directory: {exc}") from exc

        stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"{stamp}_{action.lower()}.json"
        path = backup_dir / filename

        payload: dict = {
            "action": action,
            "created_at": utcnow().isoformat(),
            "actor_id": str(getattr(actor, "id", "")),
            "actor_email": getattr(actor, "email", None),
            "tables": {},
        }
        expected_total = 0
        try:
            for model in models:
                rows = (await self.session.execute(select(model))).scalars().all()
                columns = [column.key for column in model.__table__.columns]
                serialized = [
                    {name: self._serialize(getattr(row, name)) for name in columns} for row in rows
                ]
                payload["tables"][model.__tablename__] = serialized
                expected_total += len(serialized)
            payload["total_rows"] = expected_total
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:
            raise MaintenanceError(f"Backup failed; destructive action aborted: {exc}") from exc

        # Integrity verification: re-read and confirm the row counts match.
        try:
            restored = json.loads(path.read_text(encoding="utf-8"))
            actual_total = sum(len(rows) for rows in restored.get("tables", {}).values())
        except Exception as exc:
            raise MaintenanceError(f"Backup verification failed; action aborted: {exc}") from exc
        if actual_total != expected_total:
            raise MaintenanceError(
                f"Backup verification mismatch ({actual_total} != {expected_total}); action aborted"
            )

        return {
            "path": str(path),
            "filename": filename,
            "total_rows": expected_total,
            "tables": {name: len(rows) for name, rows in payload["tables"].items()},
            "created_at": payload["created_at"],
        }

    async def count_rows(self, model) -> int:
        return int((await self.session.execute(select(func.count()).select_from(model))).scalar_one())
