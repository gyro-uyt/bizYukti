from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers tables)
from app.config import settings
from app.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # PostGIS/tiger tables and generated geog columns are managed in migrations, not the ORM.
    if type_ in ("table", "index") and reflected and compare_to is None:
        return False  # PostGIS tables and hand-written (GiST/trigram/partial) indexes live only in migrations
    if type_ == "column" and name == "geog":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True,
                      include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
