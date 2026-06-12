"""Alembic environment.

Uses the synchronous psycopg driver for migrations and pulls the DB URL from application
settings so it stays in one place. Target metadata is the full §8 model set.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Import the package so all models register on Base.metadata.
from rjacq.core.config import settings
from rjacq.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations run synchronously; strip the async marker if present. The URL is passed straight
# to SQLAlchemy (which percent-decodes the password) rather than through alembic's
# set_main_option — that routes it through ConfigParser, whose '%' interpolation rejects a
# percent-encoded password (e.g. '%21' for '!'), see migrations failing on special-char passwords.
sync_url = settings.database_url.replace("+asyncpg", "")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
