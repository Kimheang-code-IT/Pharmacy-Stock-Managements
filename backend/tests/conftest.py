# ruff: noqa: E402

import os
import tempfile
from pathlib import Path


def _env_file_value(path: Path, key: str) -> str | None:
    """Read a single KEY=VALUE from an env file without mutating the process env."""
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


# The documented local workflow generates infrastructure/.env (strong Postgres
# password) rather than exporting POSTGRES_*. Derive the test URL from it so
# `up -d db redis` + `pytest` works without hand-exporting DATABASE_URL.
if not os.environ.get("DATABASE_URL"):
    _infra_env = Path(__file__).resolve().parents[2] / "infrastructure" / ".env"
    _user = os.environ.get("POSTGRES_USER") or _env_file_value(_infra_env, "POSTGRES_USER") or "stock_pos"
    _password = os.environ.get("POSTGRES_PASSWORD") or _env_file_value(_infra_env, "POSTGRES_PASSWORD") or "stock_pos"
    _database = os.environ.get("POSTGRES_DB") or _env_file_value(_infra_env, "POSTGRES_DB") or "stock_pos"
    _test_db = _database if _database.endswith("_test") else f"{_database}_test"
    os.environ["DATABASE_URL"] = (
        f"postgresql+asyncpg://{_user}:{_password}@localhost:55432/{_test_db}"
    )
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/5")
os.environ.setdefault("SEED_ADMIN_EMAIL", "admin@gmail.com")
os.environ.setdefault("SEED_ADMIN_PASSWORD", "123456")
os.environ.setdefault("SEED_ADMIN_ENABLED", "true")
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_MINUTE", "1000")
os.environ.setdefault("RATE_LIMIT_REFRESH_PER_MINUTE", "1000")
os.environ.setdefault("RATE_LIMIT_RESET_PER_HOUR", "1000")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
# Telegram stays disabled in tests unless a test saves a token in the
# system_settings table (telegram.bot_token); no environment variable is read.
os.environ.setdefault(
    "LOCAL_STORAGE_DIR",
    tempfile.mkdtemp(prefix="stock-pos-media-"),
)
# Private backup root kept separate from the public media root.
os.environ.setdefault(
    "BACKUP_DIR",
    tempfile.mkdtemp(prefix="stock-pos-backups-"),
)

import asyncio
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_DB_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
TEST_DB_NAME = TEST_DATABASE_URL.rsplit("/", 1)[1]

# Fixed id for the default "Each" UOM seeded for tests (see tests.utils).
import uuid as _uuid

DEFAULT_UOM_ID = _uuid.UUID("00000000-0000-0000-0000-0000000000ea")


@pytest.fixture(scope="session")
def _prepare_database() -> None:
    async def _run() -> None:
        admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
        async with admin_engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
            # An interrupted pytest run can leave pooled connections holding
            # locks in the dedicated test database.  Disconnect only those
            # stale test sessions before rebuilding the schema; production and
            # development databases are never targeted here.
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": TEST_DB_NAME},
            )
        await admin_engine.dispose()

        # Authentication/reset/denylist state is intentionally transient, but
        # Redis survives between local test runs.  Start every suite with the
        # configured test Redis database empty so a previous lockout or token
        # revocation cannot cascade into unrelated failures.
        from redis.asyncio import from_url as redis_from_url

        redis_client = redis_from_url(os.environ["REDIS_URL"], decode_responses=True)
        try:
            await redis_client.flushdb()
        finally:
            await redis_client.aclose()

        from app.core import database as db_module
        from app.core.database import Base

        import app.modules.administration.models  # noqa: F401
        import app.modules.auth.models  # noqa: F401
        import app.modules.backup.models  # noqa: F401
        import app.modules.brands.models  # noqa: F401
        import app.modules.categories.models  # noqa: F401
        import app.modules.customers.models  # noqa: F401
        import app.modules.delivery.models  # noqa: F401
        import app.modules.pos.models  # noqa: F401
        import app.modules.reports.models  # noqa: F401
        import app.modules.stock.models  # noqa: F401
        import app.modules.suppliers.models  # noqa: F401
        import app.modules.telegram.models  # noqa: F401
        import app.modules.uoms.models  # noqa: F401
        import app.shared.audit.models  # noqa: F401
        import app.shared.documents.models  # noqa: F401

        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            # Drop tables outside the current metadata FIRST (e.g. a table from
            # a removed feature left in a reused test DB): a stale foreign key
            # would otherwise block drop_all from dropping the referenced table.
            leftovers = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            known = {t.lower() for t in Base.metadata.tables}
            stale = [row[0] for row in leftovers if row[0].lower() not in known]
            for table in stale:
                await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        temp_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        original_factory = db_module.SessionFactory
        db_module.SessionFactory = temp_factory
        try:
            from app.seed import seed

            await seed()

            # Deterministic default UOM for tests (products require a UOM).
            from sqlalchemy import select

            from app.modules.uoms.models import UOM

            async with temp_factory() as uom_session:
                existing = await uom_session.execute(select(UOM).where(UOM.id == DEFAULT_UOM_ID))
                if existing.scalar_one_or_none() is None:
                    uom_session.add(
                        UOM(
                            id=DEFAULT_UOM_ID,
                            code="EA",
                            name="Each",
                            symbol="ea",
                            status="ACTIVE",
                        )
                    )
                    await uom_session.commit()
        finally:
            db_module.SessionFactory = original_factory
        await engine.dispose()

    asyncio.run(_run())


@pytest_asyncio.fixture
async def db_session(_prepare_database) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(_prepare_database) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
