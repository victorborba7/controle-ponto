"""limite de tentativas de login

Cria `login_attempts`, o contador que sustenta o teto de tentativas.

Tabela sem `tenant_id` de proposito, e e a unica: ela conta tentativas que podem
nao ter tenant nenhum — quem sonda a API chuta o slug da empresa junto com a
senha. Amarrar a um tenant existente deixaria de fora justamente o trafego que
mais importa contar.

Nao ha backfill nem estado a migrar: a tabela nasce vazia e se preenche sozinha
com as falhas seguintes.

Revision ID: 0006_login_attempts
Revises: 0005_punch_config
Create Date: 2026-08-16 11:20:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_login_attempts"
down_revision: str | None = "0005_punch_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("first_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_hash", "ip_address", name="uq_login_attempts_identity_ip"),
    )
    # Os dois indices cobrem as duas regras do teto: somar as falhas de uma
    # identidade e contar identidades distintas de um endereco.
    op.create_index(
        "ix_login_attempts_identity", "login_attempts", ["identity_hash", "last_failure_at"]
    )
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip_address", "last_failure_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempts_ip", table_name="login_attempts")
    op.drop_index("ix_login_attempts_identity", table_name="login_attempts")
    op.drop_table("login_attempts")
