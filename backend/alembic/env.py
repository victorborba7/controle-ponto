"""Ambiente do Alembic, ligado ao engine assincrono da aplicacao."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.models import Base  # importar o pacote registra as tabelas no metadata

config = context.config

# A URL vem do ambiente, nunca do alembic.ini (que e versionado).
# O escape protege senhas com '%' — o ConfigParser interpretaria como interpolacao.
config.set_main_option("sqlalchemy.url", settings.database_url_str.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Ignora objetos que o pgvector cria e o autogenerate tentaria remover."""
    return not (type_ == "table" and name in {"vector"})


def _render_item(type_, obj, autogen_context):
    """Garante o import do pgvector nas migracoes geradas.

    Sem isto, o autogenerate escreve `pgvector.sqlalchemy.vector.VECTOR(...)`
    mas nao emite o import correspondente, e a migracao quebra com NameError
    na hora de aplicar.
    """
    if type_ == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
    return False  # False = seguir com a renderizacao padrao


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar ao banco (`alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detecta mudanca de tipo de coluna, nao so de nome.
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
