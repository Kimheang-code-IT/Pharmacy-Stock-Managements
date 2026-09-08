from fastapi import APIRouter

from app.api.deps import envelope
from app.core.config import settings
from app.core.redis import cache

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return envelope({"status": "ok", "environment": settings.environment})


@router.get("/health/live")
async def live() -> dict:
    return envelope({"status": "ok"})


@router.get("/health/ready")
async def ready() -> dict:
    checks: dict[str, str] = {}
    overall = True

    try:
        from sqlalchemy import text

        from app.core.database import SessionFactory

        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"
        overall = False

    checks["redis"] = "ok" if await cache.ping() else "error"
    if checks["redis"] == "error":
        overall = False

    return envelope({"status": "ok" if overall else "degraded", "checks": checks})
