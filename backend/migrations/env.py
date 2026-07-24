import os
import sys
import asyncio
from logging.config import fileConfig

# Ensure app package is discoverable on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Import your app's config and models ──────────────────────────────────────
# This is what tells Alembic about your DATABASE_URL and your table schemas.
from app.core.config import settings
from app.db.base import Base  # noqa: F401 — imports all models via __all__ or star imports

# ─────────────────────────────────────────────────────────────────────────────

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Set the SQLAlchemy URL programmatically from your Pydantic settings.
# This overrides the (intentionally blank) sqlalchemy.url in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the MetaData object Alembic uses for --autogenerate comparisons.
# It must include all your models — that's why app/db/base.py imports them all.
target_metadata = Base.metadata


# ── Offline mode (generates SQL without a live DB connection) ─────────────────
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates a .sql script instead of connecting to the DB.
    Useful for review or applying to a remote DB via psql.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Tell Alembic to render Enum types as native PostgreSQL ENUM
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connects to DB and runs migrations directly) ─────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,           # detect column type changes
        compare_server_default=True, # detect server-side default changes
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations using a sync connection wrapper.
    SQLAlchemy's Alembic integration requires a synchronous Connection object,
    so we use `run_sync` to bridge the async engine to the sync Alembic API.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool is critical for migration scripts —
                                  # don't hold connections open between statements
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — wraps the async runner."""
    asyncio.run(run_async_migrations())


# ── Dispatch ──────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()