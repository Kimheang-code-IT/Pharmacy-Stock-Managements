from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-secret-change-me-in-production-0123456789abcdef"
_DEV_TELEGRAM_SECRET = "dev-only-telegram-secret-change-me-0123456789abcdef"
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

    celery_broker_url: str = "amqp://stock_pos:stock_pos@localhost:5672/stock_pos"
    celery_result_backend: str = "redis://localhost:6379/2"

    jwt_secret_key: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    service_token_expire_minutes: int = 10

    telegram_bot_client_id: str = "stock-pos-telegram"
    telegram_bot_client_secret: str = _DEV_TELEGRAM_SECRET
    telegram_bot_token: str = ""
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

    cache_default_ttl_seconds: int = 60
    dashboard_cache_ttl_seconds: int = 60
    settings_cache_ttl_seconds: int = 120
    rate_limit_login_per_minute: int = 10
    rate_limit_refresh_per_minute: int = 30
    rate_limit_reset_per_hour: int = 5

    seed_admin_email: str = "admin@gmail.com"
    seed_admin_password: str = _DEV_SEED_PASSWORD
    seed_admin_name: str = "System Administrator"

    default_page_size: int = 20
    max_page_size: int = 100

    # Product / shop / brand images on local disk (not S3/MinIO).
    local_storage_dir: str = "var/media"
    # Archived invoice PDFs (object key stored on sales.invoice_pdf_object_key).
    invoice_storage_dir: str = "var/invoices"
    max_upload_bytes: int = 5 * 1024 * 1024

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
        if self.telegram_bot_client_secret == _DEV_TELEGRAM_SECRET or _is_placeholder_secret(self.telegram_bot_client_secret):
            problems.append("TELEGRAM_BOT_CLIENT_SECRET is still a development placeholder")
        if self.seed_admin_password == _DEV_SEED_PASSWORD or _is_placeholder_secret(self.seed_admin_password) or len(self.seed_admin_password) < 12:
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
