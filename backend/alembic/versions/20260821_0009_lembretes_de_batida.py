"""Lembretes horarios ja enviados

A tabela e o relogio do agendador. Ele roda no processo da API, numa maquina
so, e toda implantacao a reinicia — sem estado no banco, um reinicio as 9h05
reenviaria o lembrete das 9h.

A restricao unica (funcionario, dia, hora) e o que torna o envio idempotente:
duas execucoes na mesma hora colidem ali em vez de notificarem duas vezes.

`push_token` NAO entra aqui: ja existe em `devices` desde a migracao inicial,
declarada e nunca usada.

Revision ID: 0009_lembretes
Revises: 0008_dia_de_trabalho
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_lembretes"
down_revision: str | None = "0008_dia_de_trabalho"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "punch_reminders",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("employee_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("hour_index", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "employee_id",
            "business_date",
            "hour_index",
            name="uq_punch_reminders_employee_dia_hora",
        ),
    )
    op.create_index(
        "ix_punch_reminders_employee_id", "punch_reminders", ["employee_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_punch_reminders_employee_id", table_name="punch_reminders")
    op.drop_table("punch_reminders")
