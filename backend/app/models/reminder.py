"""Registro do que ja foi lembrado, para nao lembrar duas vezes.

O agendador roda dentro do processo da API, numa maquina so. Toda implantacao a
reinicia, e um reinicio as 9h05 nao pode reenviar o lembrete das 9h — nem
pular o das 10h por ter perdido o relogio interno.

A tabela e o relogio. O agendador nao guarda estado em memoria: ele pergunta ao
banco o que ja foi enviado e envia o que falta. Reiniciar deixa de ter
consequencia.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin


class PunchReminder(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Um lembrete horario ja enviado a um funcionario."""

    __tablename__ = "punch_reminders"
    __table_args__ = (
        # O coracao do mecanismo: e esta restricao que torna o envio idempotente.
        # Duas execucoes do agendador na mesma hora colidem aqui em vez de
        # notificarem duas vezes.
        UniqueConstraint(
            "employee_id",
            "business_date",
            "hour_index",
            name="uq_punch_reminders_employee_dia_hora",
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    business_date: Mapped[date] = mapped_column(nullable=False)

    #: Quantas horas cheias haviam se passado desde a entrada do dia. 1 e o
    #: lembrete de uma hora depois de entrar.
    hour_index: Mapped[int] = mapped_column(Integer, nullable=False)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<PunchReminder {self.employee_id} {self.business_date} +{self.hour_index}h>"
