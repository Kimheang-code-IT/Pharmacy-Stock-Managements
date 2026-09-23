import json
import logging
import secrets
from datetime import timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccessDeniedError,
    AuthRequiredError,
    ConflictError,
    RateLimitedError,
    ValidationError,
)
from app.core.permissions import SUPER_ADMIN_ROLE
from app.core.rate_limit import RateLimited, enforce_rate_limit
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_password_reset_jwt,
    create_refresh_token,
    decode_token,
    generate_reset_code,
    hash_password,
    hash_token,
    utcnow,
    validate_password_strength,
    verify_password,
)
from app.modules.administration import get_setting_value
from app.modules.auth.models import User
from app.modules.auth.repository import RoleRepository, UserRepository
from app.modules.auth.schemas import (
    TokenPairResponse,
    UserOut,
    token_pair_payload,
)
from app.shared.audit.service import record_audit

logger = logging.getLogger("stock_pos.auth")

RESET_CODE_PREFIX = "pwreset"
REFRESH_DENYLIST_PREFIX = "jwt:revoked"
HANDOFF_PREFIX = "pwhandoff"
TELEGRAM_LINK_PREFIX = "tglink"

_GENERIC_RESET_MESSAGE = (
    "If the email exists and Telegram delivery is configured, a verification code has been sent."
)


def user_to_out(user: User) -> UserOut:
    from app.core.permissions import effective_permissions

    return UserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        telegram_chat_id=user.telegram_chat_id,
        telegram_name=user.telegram_name,
        telegram_verified=user.telegram_verified,
        status=user.status,
        role=user.role_ref.name if user.role_ref else None,
        permissions=effective_permissions(user),
        last_login_at=user.last_login_at,
        avatar=user.avatar,
        must_change_password=bool(getattr(user, "must_change_password", False)),
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)

    # ------------------------------------------------------------------ setup

    async def setup_completed(self) -> bool:
        return await self.users.any_user_exists()

    async def setup(self, payload, *, ip_address: str | None, user_agent: str | None) -> UserOut:
        # Serialize the one-time setup: without a lock two concurrent
        # unauthenticated POST /auth/setup requests can both create a user.
        from sqlalchemy import text

        await self.session.execute(text("SELECT pg_advisory_xact_lock(914627)"))
        if await self.users.any_user_exists():
            raise ConflictError("Initial setup has already been completed")

        await self.roles.ensure_administrator_role()
        admin_role = await self.roles.get_by_name(SUPER_ADMIN_ROLE)
        if admin_role is None:
            raise ConflictError("Administrator role could not be created")

        try:
            validate_password_strength(payload.password)
        except ValueError as exc:
            raise ValidationError(str(exc), field_errors={"password": str(exc)})

        user = User(
            full_name=payload.full_name.strip(),
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            telegram_chat_id=payload.telegram_chat_id,
            telegram_verified=False,
            role_id=admin_role.id,
            status="ACTIVE",
            password_changed_at=utcnow(),
        )
        await self.users.create(user)
        await record_audit(
            self.session,
            action="initial_setup",
            module="auth",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            new_values={"email": user.email, "role": admin_role.name},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.commit()
        return user_to_out(user)

    # ------------------------------------------------------------------ login

    async def login(self, payload, *, ip_address: str | None, user_agent: str | None) -> TokenPairResponse:
        try:
            await enforce_rate_limit(
                f"login:{ip_address}:{payload.email.lower()}",
                settings.rate_limit_login_per_minute,
                60,
            )
        except RateLimited:
            raise RateLimitedError("Too many login attempts. Try again later.")

        user = await self.users.get_by_email(payload.email)
        await self._ensure_not_locked(user, payload.email)
        if user is None or not verify_password(user.password_hash, payload.password):
            await self._audit_failed_login(payload.email, ip_address, user_agent)
            await self._register_failed_login(user, payload.email)
            raise AuthRequiredError("Invalid email or password")
        if user.status != "ACTIVE":
            # Audit disabled-account attempts like any other failed login.
            await self._audit_failed_login(payload.email, ip_address, user_agent)
            raise AccessDeniedError("This account is disabled")

        # Forced / expired password change (blocks other actions until done).
        await self._evaluate_password_change(user)

        tokens = await self._issue_tokens(user)
        await self._clear_failed_login(user)
        await self.users.set_last_login(user)
        await record_audit(
            self.session,
            action="login",
            module="auth",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.commit()
        return token_pair_payload(TokenPairResponse(
            access_token=tokens[0],
            refresh_token=tokens[1],
            expires_in=settings.access_token_expire_minutes * 60,
            user=user_to_out(user),
        ))

    async def _audit_failed_login(self, email: str, ip_address: str | None, user_agent: str | None) -> None:
        await record_audit(
            self.session,
            action="login_failed",
            module="auth",
            entity_type="user",
            new_values={"email": email.lower()},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.commit()

    async def _security_int(self, key: str, default: int) -> int:
        try:
            return int(await get_setting_value(self.session, "security", key, default))
        except (TypeError, ValueError):
            return default

    async def _ensure_not_locked(self, user: User | None, email: str) -> None:
        # DB-backed lockout (authoritative; survives Redis being unavailable).
        if user is not None and user.locked_until is not None:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > utcnow():
                raise RateLimitedError("Account temporarily locked. Try again later.")
        # Redis fallback also covers unknown emails.
        client = get_redis()
        try:
            if await client.exists(f"loginlock:{email.lower()}"):
                raise RateLimitedError("Account temporarily locked. Try again later.")
        except RateLimitedError:
            raise
        except Exception:
            return

    async def _register_failed_login(self, user: User | None, email: str) -> None:
        max_attempts = await self._security_int("max_login_attempts", 5)
        if max_attempts <= 0:
            return
        lock_minutes = await self._security_int("account_lock_minutes", 15)
        if user is not None:
            # Never lock the final active Administrator out of the system.
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= max_attempts:
                if not await self._is_last_active_admin(user):
                    user.locked_until = utcnow() + timedelta(minutes=max(1, lock_minutes))
                user.failed_login_attempts = 0
            await self.session.flush()
            # Persist the counter/lock: the caller raises, so commit here.
            await self.session.commit()
            return
        # Unknown email: Redis-only counting (the account does not exist, so a
        # DB lockout is meaningless).
        client = get_redis()
        key = f"loginfail:{email.lower()}"
        window = max(60, lock_minutes * 60)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, window)
            if count >= max_attempts:
                await client.set(f"loginlock:{email.lower()}", "1", ex=window)
                await client.delete(key)
        except Exception:
            return

    async def _clear_failed_login(self, user: User | None) -> None:
        if user is not None and ((user.failed_login_attempts or 0) or user.locked_until):
            user.failed_login_attempts = 0
            user.locked_until = None
            await self.session.flush()
        if user is None:
            return
        client = get_redis()
        try:
            await client.delete(f"loginfail:{user.email.lower()}")
        except Exception:
            pass

    async def _is_last_active_admin(self, user: User) -> bool:
        from app.modules.auth.models import Role

        if user.role_ref is None or user.role_ref.name != SUPER_ADMIN_ROLE or user.status != "ACTIVE":
            return False
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .join(Role, Role.id == User.role_id)
            .where(
                Role.name == SUPER_ADMIN_ROLE,
                User.status == "ACTIVE",
                User.id != user.id,
            )
        )
        return int(result.scalar_one()) == 0

    async def _evaluate_password_change(self, user: User) -> bool:
        """Mark the account as requiring a password change when forced/expired."""
        if getattr(user, "must_change_password", False):
            return True
        require_change = bool(
            await get_setting_value(self.session, "security", "require_password_change", False)
        )
        if require_change and user.password_changed_at is None:
            user.must_change_password = True
            await self.session.flush()
            return True
        expiry_days = await self._security_int("password_expiry_days", 0)
        if expiry_days > 0 and user.password_changed_at is not None:
            changed = user.password_changed_at
            if changed.tzinfo is None:
                changed = changed.replace(tzinfo=timezone.utc)
            if (utcnow() - changed).days >= expiry_days:
                user.must_change_password = True
                await self.session.flush()
                return True
        return False

    async def _issue_tokens(self, user: User) -> tuple[str, str]:
        refresh_days = await self._security_int("jwt_refresh_token_days", settings.refresh_token_expire_days)
        access, _, _ = create_access_token(user.id, {"ver": user.token_version})
        refresh, _, _, _ = create_refresh_token(
            user.id, extra_claims={"ver": user.token_version}, expire_days=refresh_days
        )
        return access, refresh

    # ---------------------------------------------------------------- refresh

    async def refresh(self, refresh_token: str) -> TokenPairResponse:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception as exc:
            raise AuthRequiredError("Invalid or expired refresh token") from exc

        if await self._is_revoked(payload["jti"]):
            raise AuthRequiredError("Invalid or expired refresh token")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if user is None or user.status != "ACTIVE" or payload.get("ver") != user.token_version:
            raise AuthRequiredError("Invalid or expired refresh token")

        # Revocation TTL must cover the full configurable refresh lifetime,
        # otherwise a rotated JTI could be replayed after the denylist entry
        # expires but before the token itself expires.
        refresh_days = await self._security_int("jwt_refresh_token_days", settings.refresh_token_expire_days)
        await self._revoke(payload["jti"], refresh_days * 86400)
        access, _, _ = create_access_token(user.id, {"ver": user.token_version})
        new_refresh, _, _, _ = create_refresh_token(
            user.id, extra_claims={"ver": user.token_version}, expire_days=refresh_days
        )
        await self.session.commit()
        return token_pair_payload(TokenPairResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=settings.access_token_expire_minutes * 60,
            user=user_to_out(user),
        ))

    async def logout(self, user: User, refresh_token: str | None) -> None:
        if refresh_token:
            try:
                payload = decode_token(refresh_token, expected_type="refresh")
                if payload.get("sub") == str(user.id):
                    try:
                        already_revoked = await self._is_revoked(payload["jti"])
                    except AuthRequiredError:
                        # Denylist unreachable: revocation is best-effort here,
                        # the client still ends its session.
                        already_revoked = True
                    if not already_revoked:
                        refresh_days = await self._security_int(
                            "jwt_refresh_token_days", settings.refresh_token_expire_days
                        )
                        await self._revoke(payload["jti"], refresh_days * 86400)
            except Exception:
                pass
        await self.session.commit()

    async def _is_revoked(self, jti: str) -> bool:
        client = get_redis()
        try:
            return bool(await client.exists(f"{REFRESH_DENYLIST_PREFIX}:{jti}"))
        except Exception as exc:
            # Fail CLOSED: without the denylist we cannot prove a rotated JTI
            # is still valid, so a refresh must be rejected (security over
            # availability). Rate limits stay fail-open separately.
            logger.error("Refresh denylist unavailable (%s); rejecting refresh", exc)
            raise AuthRequiredError("Token revocation store unavailable") from exc

    async def _revoke(self, jti: str, ttl_seconds: int) -> None:
        client = get_redis()
        try:
            await client.set(f"{REFRESH_DENYLIST_PREFIX}:{jti}", "1", ex=ttl_seconds)
        except Exception as exc:
            logger.warning("Failed to revoke token %s: %s", jti, exc)

    # ---------------------------------------------------------- password reset

    async def forgot_password(self, email: str, *, ip_address: str | None) -> dict:
        try:
            await enforce_rate_limit(
                f"pwreset:{ip_address}:{email.lower()}", settings.rate_limit_reset_per_hour, 3600
            )
        except RateLimited:
            return {"message": _GENERIC_RESET_MESSAGE, "channel": "telegram"}

        user = await self.users.get_by_email(email)
        if user is None:
            return {"message": _GENERIC_RESET_MESSAGE, "channel": "telegram"}

        # No linked Telegram chat yet: hand out a one-time /link code. The user
        # sends it to the bot and the bot replies with the reset code (the
        # account has no other delivery channel).
        if not user.telegram_chat_id:
            link_code, link_ttl = await self.create_telegram_link_code(user, for_reset=True)
            await record_audit(
                self.session,
                action="password_reset_link_requested",
                module="auth",
                user_id=user.id,
                entity_type="user",
                entity_id=user.id,
                ip_address=ip_address,
            )
            await self.session.commit()
            return {
                "message": _GENERIC_RESET_MESSAGE,
                "channel": "telegram_link",
                "link_code": link_code,
                "expires_in": link_ttl,
            }

        try:
            code, ttl_minutes, handoff_token = await self.issue_reset_code(user)
        except Exception as exc:
            logger.error("Failed to persist reset code state: %s", exc)
            return {"message": _GENERIC_RESET_MESSAGE, "channel": "telegram"}

        from app.shared.telegram import queue_reset_code_delivery

        queue_reset_code_delivery(
            user.telegram_chat_id,
            code,
            handoff_token=handoff_token or None,
            minutes=ttl_minutes,
        )
        await record_audit(
            self.session,
            action="password_reset_requested",
            module="auth",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip_address,
        )
        await self.session.commit()
        return {"message": _GENERIC_RESET_MESSAGE, "channel": "telegram"}

    async def issue_reset_code(self, user: User) -> tuple[str, int, str | None]:
        """Generate a reset code + Telegram handoff token, stored in Redis.

        Returns `(code, ttl_minutes, handoff_token)`. Never writes PostgreSQL,
        so the Telegram bot can reuse it after linking a chat.
        """
        code = generate_reset_code()
        ttl_minutes = await self._security_int(
            "password_reset_code_expiry_minutes", settings.telegram_reset_code_expire_minutes
        )
        ttl_seconds = max(60, ttl_minutes * 60)
        client = get_redis()
        state = {"code_hash": hash_token(code), "attempts": 0, "used": False}
        await client.set(
            f"{RESET_CODE_PREFIX}:{user.id}",
            json.dumps(state),
            ex=ttl_seconds,
        )

        # Single-use handoff token for the Telegram deep link
        # (<frontend>/auth/reset-password?handoff=…). It exchanges for the
        # same reset-token flow as verifying the code manually.
        handoff_token = secrets.token_urlsafe(24)
        try:
            await client.set(
                f"{HANDOFF_PREFIX}:{handoff_token}",
                json.dumps({"user_id": str(user.id)}),
                ex=ttl_seconds,
            )
        except Exception as exc:
            logger.error("Failed to persist reset handoff token: %s", exc)
            handoff_token = None
        return code, ttl_minutes, handoff_token

    async def verify_reset_code(self, email: str, code: str) -> tuple[str, int]:
        user = await self.users.get_by_email(email)
        state = await self._load_reset_state(user.id) if user else None
        if user is None or state is None:
            raise ValidationError("Invalid or expired verification code")
        if state.get("used"):
            raise ConflictError("This verification code has already been used")

        if state.get("code_hash") != hash_token(code):
            await self._register_failed_attempt(user.id, state)
            raise ValidationError("Invalid or expired verification code")

        reset_token, expires = create_password_reset_jwt(user.id, code_hash=state["code_hash"])
        return reset_token, max(int((expires - utcnow()).total_seconds()), 0)

    async def reset_password(self, reset_token: str, new_password: str) -> None:
        try:
            payload = decode_token(reset_token, expected_type="password_reset")
        except Exception as exc:
            raise ValidationError("Invalid or expired reset token") from exc

        user = await self.users.get_by_id(UUID(payload["sub"]))
        state = await self._load_reset_state(user.id) if user else None
        if user is None or state is None:
            raise ValidationError("Invalid or expired reset token")
        if state.get("used"):
            raise ConflictError("This verification code has already been used")
        if state.get("code_hash") != payload.get("ch"):
            raise ValidationError("Invalid or expired reset token")

        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            raise ValidationError(str(exc), field_errors={"new_password": str(exc)})
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.users.bump_token_version(user)
        await self._mark_reset_state_used(user.id)
        await record_audit(
            self.session,
            action="password_reset_completed",
            module="auth",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        await self.session.commit()

    async def _load_reset_state(self, user_id: UUID) -> dict | None:
        client = get_redis()
        try:
            raw = await client.get(f"{RESET_CODE_PREFIX}:{user_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error("Failed to load reset state: %s", exc)
            return None

    async def _register_failed_attempt(self, user_id: UUID, state: dict) -> None:
        state["attempts"] = int(state.get("attempts", 0)) + 1
        client = get_redis()
        try:
            ttl = await client.ttl(f"{RESET_CODE_PREFIX}:{user_id}")
            if state["attempts"] >= settings.telegram_reset_max_attempts:
                await client.delete(f"{RESET_CODE_PREFIX}:{user_id}")
            else:
                await client.set(
                    f"{RESET_CODE_PREFIX}:{user_id}", json.dumps(state), ex=max(ttl, 1)
                )
        except Exception as exc:
            logger.error("Failed to update reset attempts: %s", exc)

    async def _mark_reset_state_used(self, user_id: UUID) -> None:
        client = get_redis()
        try:
            state = await self._load_reset_state(user_id)
            if state is None:
                return
            state["used"] = True
            ttl = await client.ttl(f"{RESET_CODE_PREFIX}:{user_id}")
            await client.set(f"{RESET_CODE_PREFIX}:{user_id}", json.dumps(state), ex=max(ttl, 1))
        except Exception as exc:
            logger.error("Failed to mark reset code used: %s", exc)

    # -------------------------------------------------- handoff / profile / link

    async def exchange_handoff(self, handoff_token: str) -> tuple[User, str, int]:
        """Exchange a Telegram deep-link handoff token for (user, reset_token,
        expires_in). Single use: the handoff token is consumed, the reset
        session stays valid until the password is actually reset."""
        client = get_redis()
        try:
            raw = await client.get(f"{HANDOFF_PREFIX}:{handoff_token}")
        except Exception as exc:
            logger.error("Failed to load handoff token: %s", exc)
            raw = None
        if not raw:
            raise ValidationError("Invalid or expired reset link")
        data = json.loads(raw)
        user = await self.users.get_by_id(UUID(data["user_id"]))
        state = await self._load_reset_state(user.id) if user else None
        if user is None or state is None:
            raise ValidationError("Invalid or expired reset link")
        if state.get("used"):
            raise ConflictError("This verification code has already been used")

        try:
            await client.delete(f"{HANDOFF_PREFIX}:{handoff_token}")
        except Exception as exc:
            logger.error("Failed to consume handoff token: %s", exc)

        reset_token, expires = create_password_reset_jwt(user.id, code_hash=state["code_hash"])
        return user, reset_token, max(int((expires - utcnow()).total_seconds()), 0)

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Authenticated self-service password change. Bumps the token
        version so other sessions are signed out."""
        if not verify_password(user.password_hash, current_password):
            raise ValidationError(
                "Current password is incorrect",
                field_errors={"current_password": "Incorrect password"},
            )
        if current_password == new_password:
            raise ValidationError("New password must differ from the current password")
        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            raise ValidationError(str(exc), field_errors={"new_password": str(exc)})
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.users.bump_token_version(user)
        await record_audit(
            self.session,
            action="password_changed",
            module="auth",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        await self.session.commit()

    async def update_avatar(self, user: User, avatar: str | None) -> User:
        """Set or clear the profile avatar (image reference only — never a
        binary blob in PostgreSQL)."""
        value = (avatar or "").strip() or None
        if value and not value.startswith(("data:image/", "/api/v1/images/", "http://", "https://")):
            raise ValidationError("Invalid avatar reference", field_errors={"avatar": "Invalid avatar"})
        if value and len(value) > 2_000_000:
            raise ValidationError("Avatar is too large", field_errors={"avatar": "Too large"})
        user.avatar = value
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def create_telegram_link_code(self, user: User, *, for_reset: bool = False) -> tuple[str, int]:
        """One-time code the user sends to the bot (`/link CODE`) to bind this
        chat to their account. Stored in Redis, never in PostgreSQL.

        When `for_reset` is true the bot replies with a password-reset code
        right after linking (account recovery without a prior Telegram link)."""
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        ttl_seconds = settings.telegram_link_code_expire_minutes * 60
        payload: dict = {"user_id": str(user.id)}
        if for_reset:
            payload["reset"] = True
        client = get_redis()
        try:
            await client.set(
                f"{TELEGRAM_LINK_PREFIX}:{code}",
                json.dumps(payload),
                ex=ttl_seconds,
            )
        except Exception as exc:
            logger.error("Failed to persist telegram link code: %s", exc)
            raise ValidationError("Could not create a link code right now") from exc
        return code, ttl_seconds
