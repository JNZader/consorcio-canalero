from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy import create_engine

from alembic import context

from app.config import settings
from app.db.base import Base

# Import all models so Alembic autogenerate detects them
from app.auth.models import User  # noqa: F401
from app.domains.denuncias.models import Denuncia, DenunciaHistorial  # noqa: F401
from app.domains.infraestructura.models import Asset, MantenimientoLog  # noqa: F401
from app.domains.finanzas.models import Gasto, Ingreso, Presupuesto  # noqa: F401
from app.domains.padron.models import Consorcista  # noqa: F401
from app.domains.tramites.models import Tramite, TramiteSeguimiento  # noqa: F401
from app.domains.capas.models import Capa  # noqa: F401

# Alembic Config object
config = context.config

# Setup loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
