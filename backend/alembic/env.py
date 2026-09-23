import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

# Import every model module so Base.metadata is fully populated before Alembic
# compares it against the database. Without these, autogenerate/check compare
# against an empty schema and can never detect model<->migration drift.
import app.modules.administration.models  # noqa: F401,E402
import app.modules.auth.models  # noqa: F401,E402
import app.modules.backup.models  # noqa: F401,E402
import app.modules.brands.models  # noqa: F401,E402
import app.modules.categories.models  # noqa: F401,E402
import app.modules.customers.models  # noqa: F401,E402
import app.modules.delivery.models  # noqa: F401,E402
import app.modules.pos.models  # noqa: F401,E402
import app.modules.reports.models  # noqa: F401,E402
import app.modules.stock.models  # noqa: F401,E402
import app.modules.suppliers.models  # noqa: F401,E402
import app.modules.telegram.models  # noqa: F401,E402
import app.modules.uoms.models  # noqa: F401,E402
import app.shared.audit.models  # noqa: F401,E402
import app.shared.documents.models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.sync_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
