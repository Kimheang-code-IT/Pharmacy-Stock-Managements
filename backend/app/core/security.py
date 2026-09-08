import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_reset_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def create_access_token(user_id: int, extra_claims: dict[str, Any] | None = None) -> tuple[str, datetime, str]:
    now = utcnow()
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires, jti


def create_refresh_token(
    user_id: int | str, family_id: str | None = None, extra_claims: dict[str, Any] | None = None
) -> tuple[str, datetime, str, str]:
    now = utcnow()
    expires = now + timedelta(days=settings.refresh_token_expire_days)
    jti = uuid.uuid4().hex
    family = family_id or uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "fam": family,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires, jti, family


def create_service_token(client_id: str) -> tuple[str, datetime]:
    now = utcnow()
    expires = now + timedelta(minutes=settings.service_token_expire_minutes)
    payload = {
        "sub": client_id,
        "type": "service",
        "scope": "telegram.reports.read",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires


def create_password_reset_jwt(user_id: int, code_hash: str | None = None) -> tuple[str, datetime]:
    now = utcnow()
    expires = now + timedelta(minutes=10)
    payload = {
        "sub": str(user_id),
        "type": "password_reset",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if code_hash:
        payload["ch"] = code_hash
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected {expected_type} token")
    return payload


def hash_password(password: str) -> str:
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError

    try:
        ph = PasswordHasher()
        ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, ValueError):
        return False
