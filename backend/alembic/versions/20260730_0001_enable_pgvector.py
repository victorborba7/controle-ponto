"""Habilita a extensao pgvector

Migracao separada do schema de proposito: a extensao precisa existir antes de
qualquer CREATE TABLE que use o tipo `vector`, e mante-la isolada deixa claro
que e um pre-requisito de infraestrutura, nao parte do modelo de dominio.

Revision ID: 0001_pgvector
Revises:
Create Date: 2026-07-30

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0001_pgvector"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Sem DROP EXTENSION: derrubaria qualquer coluna vector ainda existente.
    # Remover a extensao e operacao manual e deliberada.
    pass
