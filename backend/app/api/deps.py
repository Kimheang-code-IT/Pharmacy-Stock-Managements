from uuid import UUID

from fastapi import Depends, Query, Request
from fastapi.security import HTTPBearer
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory, get_session
from app.core.exceptions import AccessDeniedError, AuthRequiredError
from app.core.permissions import user_has_permission
from app.core.redis import get_redis
from app.core.security import decode_token
from app.shared.pagination.params import ListParams, envelope, parse_date_range

__all__ = [
    "ListParams",
    "envelope",
    "get_db",
    "get_db_session",
    "get_current_user",
    "get_redis_dep",
    "list_params",
    "parse_date_range",
    "require_permission",
]

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> AsyncSession:
    return get_session()


async def get_db_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session


async def get_redis_dep() -> aioredis.Redis | None:
    try:
        return get_redis()
    except Exception:
        return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    credentials=Depends(_bearer_scheme),
):
    from app.modules.auth.models import User
    from app.modules.auth.repository import UserRepository

    if credentials is None or not credentials.credentials:
        raise AuthRequiredError()
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except Exception as exc:
        raise AuthRequiredError() from exc

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthRequiredError() from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise AuthRequiredError()
    if user.status != "ACTIVE":
        raise AccessDeniedError("This account is disabled")
    if payload.get("ver") != user.token_version:
        raise AuthRequiredError()
    request.state.user = user
    return user


def require_permission(permission: str):
    async def checker(user=Depends(get_current_user)):
        if not user_has_permission(user, permission):
            raise AccessDeniedError()
        return user

    return checker


# Re-export ListParams defaults wired to settings for FastAPI Depends usage.
def list_params(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    sort: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_date: str | None = Query(default=None, alias="startDate"),
    end_date: str | None = Query(default=None, alias="endDate"),
) -> ListParams:
    return ListParams(
        q=q,
        page=page,
        limit=limit,
        sort=sort,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
