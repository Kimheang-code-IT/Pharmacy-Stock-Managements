import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AccessDeniedError, AuthRequiredError
from app.core.logging import setup_logging
from app.core.redis import close_redis
from app.core.scheduler import start_backend_scheduler
from app.shared.audit.service import RESULT_DENIED, record_audit, set_audit_context

setup_logging()
logger = logging.getLogger("stock_pos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_safe_for_production()
    logger.info("Stock & POS API starting (%s)", settings.environment)
    # Keep the permission catalog and Administrator role in sync after code updates
    # (e.g. replacing legacy *.manage codes with View/Add/Edit/Delete).
    try:
        from app.core.database import SessionFactory
        from app.modules.auth.repository import RoleRepository

        async with SessionFactory() as session:
            await RoleRepository(session).ensure_administrator_role()
            await session.commit()
    except Exception:
        logger.exception("Failed to sync permission catalog / Administrator role on startup")
    stop_scheduler = None
    scheduler_task = None
    if settings.scheduler_enabled:
        stop_scheduler, scheduler_task = start_backend_scheduler()
    try:
        yield
    finally:
        if stop_scheduler is not None:
            stop_scheduler.set()
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        await close_redis()
        logger.info("Stock & POS API stopped")


def _client_ip(request: Request) -> str | None:
    """Client IP for auditing. Trusts the last X-Forwarded-For hop only (the
    proxy appends the real client), never the spoofable first entry."""
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else None


def create_app() -> FastAPI:
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    cors_kwargs: dict = {
        "allow_origins": settings.cors_origin_list,
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if settings.environment == "development" and settings.cors_allow_private_networks:
        cors_kwargs["allow_origin_regex"] = (
            r"https?://("
            r"localhost|127\.0\.0\.1"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
            r")(:\d+)?$"
        )
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        # Propagate request context so every audit row written downstream is
        # attributed with the correlation id, IP and user agent.
        set_audit_context(
            request_id=request_id,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    async def _audit_denied(request: Request, exc: Exception) -> None:
        """Persist a denied/failed authorization attempt (best effort)."""
        try:
            from app.core.database import SessionFactory

            user = getattr(request.state, "user", None)
            status_code = getattr(exc, "status_code", 403)
            action = "authentication_failed" if status_code == 401 else "permission_denied"
            async with SessionFactory() as session:
                await record_audit(
                    session,
                    action=action,
                    module="security",
                    user_id=getattr(user, "id", None),
                    actor_email=getattr(user, "email", None),
                    entity_type="http_request",
                    new_values={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                    },
                    result=RESULT_DENIED,
                )
                await session.commit()
        except Exception:
            logger.warning("Failed to persist denied-request audit", exc_info=True)

    @app.exception_handler(AccessDeniedError)
    async def access_denied_handler(request: Request, exc: AccessDeniedError):
        await _audit_denied(request, exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(AuthRequiredError)
    async def auth_required_handler(request: Request, exc: AuthRequiredError):
        await _audit_denied(request, exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError):
        field_errors: dict[str, str] = {}
        for error in exc.errors():
            key = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path"))
            field_errors.setdefault(key, str(error.get("msg", "Invalid value")))
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "field_errors": field_errors,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": str(exc.detail),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
