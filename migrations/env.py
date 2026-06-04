from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from finances.core.database import Base, engine
from finances.models import (  # noqa: F401 — registers all models with Base.metadata
    Account,
    CashWithdrawal,
    Category,
    Installment,
    InstallmentPlan,
    Label,
    SavingsPocket,
    SavingsPocketMovement,
    Statement,
    Transaction,
    Transfer,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        _run_with_connection(connection)


def _run_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
