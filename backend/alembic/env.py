from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models_sqlalchemy import Base
from app.models_sqlalchemy.models import (
    User, Buying, Warehouse, SKU, Listing, Inventory, Return,
    SyncLog, Report, PasswordResetToken
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

from app.config import settings
database_url = settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get connection args for Supabase (same as in models_sqlalchemy)
    connect_args = {}
    # database_url is set above from settings.DATABASE_URL
    if "postgresql" in database_url or "postgres" in database_url:
        connect_args = {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    
    # Get config section and add connect_args
    configuration = config.get_section(config.config_ini_section, {})
    if connect_args:
        # Add connect_args to configuration (engine_from_config will use them)
        for key, value in connect_args.items():
            configuration[f"connect_args.{key}"] = str(value)
    
    # Create engine with optimized settings for Supabase
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Use NullPool for migrations (single connection)
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
