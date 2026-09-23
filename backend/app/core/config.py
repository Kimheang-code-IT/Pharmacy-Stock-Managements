from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-secret-change-me-in-production-0123456789abcdef"
_DEV_SEED_PASSWORD = "123456"


def _is_placeholder_secret(value: str) -> bool:
    stripped = (value or "").strip()
    return not stripped or stripped.startswith("CHANGE_ME") or stripped.startswith("dev-only")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Stock & POS API"
    debug: bool = True
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://stock:stock@localhost:5432/stock_pos"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    # Keep users signed in for a full day; the refresh token (below) renews the
    # session seamlessly when the access token eventually expires.
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    telegram_bot_token: str = ""
    telegram_bot_mode: str = "polling"
    telegram_enabled: bool = True
    telegram_reset_code_expire_minutes: int = 5
    telegram_reset_max_attempts: int = 5
    telegram_link_code_expire_minutes: int = 10
    # Public SPA origin, used to build the Telegram reset-password deep link.
    frontend_base_url: str = ""
    # Hour (UTC) for the daily expiry alert sweep. Runs in this API process.
    expiry_alert_scan_hour: int = 7
    scheduler_enabled: bool = True

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_private_networks: bool = True

    dashboard_cache_ttl_seconds: int = 60
    rate_limit_login_per_minute: int = 10
    rate_limit_refresh_per_minute: int = 30
    rate_limit_reset_per_hour: int = 5

    # Bootstrap the first administrator from SEED_ADMIN_* on startup. Disabled
    # by default so a fresh install shows the Initial Setup page and the first
    # registered user becomes the Administrator.
    seed_admin_enabled: bool = False
    seed_admin_email: str = "admin@gmail.com"
    seed_admin_password: str = _DEV_SEED_PASSWORD
    seed_admin_name: str = "System Administrator"

    default_page_size: int = 20
    # Report list endpoints group line-level rows into documents client-side,
    # so they request a wide page; keep the server-side cap generous.
    max_page_size: int = 500

    # Product / shop / brand images on local disk (not S3/MinIO). This root is
    # served (publicly) by GET /api/v1/images/{key}, so it must contain ONLY
    # publicly-renderable images.
    local_storage_dir: str = "var/media"
    max_upload_bytes: int = 5 * 1024 * 1024
    # Private operational snapshots (maintenance/reset backups). Deliberately
    # OUTSIDE local_storage_dir: never served by the image route.
    backup_dir: str = "var/backups"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    def assert_safe_for_production(self) -> None:
        """Refuse to boot with development secrets when ENVIRONMENT=production."""
        if not self.is_production:
            return

        problems: list[str] = []
        if self.jwt_secret_key == _DEV_JWT_SECRET or _is_placeholder_secret(self.jwt_secret_key) or len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY is missing, too short, or still a development placeholder")
        if self.seed_admin_enabled and (
            self.seed_admin_password == _DEV_SEED_PASSWORD
            or _is_placeholder_secret(self.seed_admin_password)
            or len(self.seed_admin_password) < 12
        ):
            problems.append("SEED_ADMIN_PASSWORD is too weak or still a development placeholder")
        if self.debug:
            problems.append("DEBUG must be false in production")
        if self.cors_allow_private_networks:
            problems.append("CORS_ALLOW_PRIVATE_NETWORKS must be false in production")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
