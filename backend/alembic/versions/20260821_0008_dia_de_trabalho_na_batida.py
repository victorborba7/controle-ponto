"""A que dia de trabalho cada batida pertence

Ate aqui "o dia" era o dia UTC, por omissao: `tenants.timezone` existia e
ninguem lia. Na Florida (UTC-4) isso poe uma batida das 20h de terca na
quarta-feira, e a jornada de terca sai menor do que foi trabalhada.

O backfill converte o historico usando o fuso de cada tenant. `AT TIME ZONE`
sobre uma coluna `timestamptz` devolve o horario local correspondente, entao
`::date` da o dia como a empresa o enxerga.

Nao ha ALTER de enum nesta migracao mesmo com `EntryType.INTERMEDIATE` sendo
adicionado junto: `enum_column` usa `native_enum=False` e o SQLAlchemy 2.0 so
cria a CHECK com `create_constraint=True`, que nao e o padrao. A coluna e
VARCHAR(20) sem restricao — conferido no banco antes de escrever isto.

Revision ID: 0008_dia_de_trabalho
Revises: 0007_limiar_por_tenant
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_dia_de_trabalho"
down_revision: str | None = "0007_limiar_por_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Em tres passos: nulavel, preenche, exige. Criar ja NOT NULL falharia em
    # qualquer base com historico.
    op.add_column("time_entries", sa.Column("business_date", sa.Date(), nullable=True))

    op.execute(
        """
        UPDATE time_entries AS te
        SET business_date = (
            te.recorded_at AT TIME ZONE COALESCE(NULLIF(t.timezone, ''), 'UTC')
        )::date
        FROM tenants AS t
        WHERE te.tenant_id = t.id
        """
    )

    # Rede de seguranca para linha orfa de tenant (nao deveria existir, mas o
    # NOT NULL abaixo falharia sem explicar por que).
    op.execute(
        "UPDATE time_entries SET business_date = (recorded_at AT TIME ZONE 'UTC')::date "
        "WHERE business_date IS NULL"
    )

    op.alter_column("time_entries", "business_date", nullable=False)

    op.create_index(
        "ix_time_entries_tenant_employee_dia",
        "time_entries",
        ["tenant_id", "employee_id", "business_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_time_entries_tenant_employee_dia", table_name="time_entries")
    op.drop_column("time_entries", "business_date")
