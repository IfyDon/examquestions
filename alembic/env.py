from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import DATABASE_URL
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    if type_ == "table" and name in {
        "questions",
        "jamb_questions",
        "waec_questions",
        "neco_questions",
        "demo_questions",
    }:
        return False
    return True


def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
