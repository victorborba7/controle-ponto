"""Como a empresa quer que o ponto seja batido.

O gesto de bater ponto e o mesmo em toda empresa; o que se registra junto nao
e. Uma quer justificativa de atraso, outra quer distinguir "saida para campo"
de "saida do expediente", e a maioria nao quer campo nenhum atrapalhando quem
so quer bater e entrar.

A configuracao e **por empresa**, nao por local: o modo de bater ponto costuma
ser politica da companhia, e um funcionario que circula entre o hangar e o
escritorio nao deveria ver telas diferentes conforme onde esta.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import EntryType, LabelMode, NoteMode

#: Teto da observacao. Generoso para uma justificativa, curto o bastante para
#: nao virar deposito de texto — e para caber na tela do RH sem rolagem.
NOTE_MAX_LENGTH = 500

#: Teto do rotulo. Ele aparece como botao na tela do funcionario e como coluna
#: no relatorio; nome longo quebra os dois.
LABEL_MAX_LENGTH = 60


class PunchConfig(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Configuracao de batida da empresa. Uma por tenant.

    Ausencia de linha significa o padrao — batida simples, sem campo nenhum.
    Nao ha migracao de dados a fazer para quem ja usa o sistema.
    """

    __tablename__ = "punch_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_punch_configs_tenant"),)

    note_mode: Mapped[NoteMode] = mapped_column(
        enum_column(NoteMode, "note_mode", length=20),
        nullable=False,
        default=NoteMode.HIDDEN,
    )
    note_prompt: Mapped[str | None] = mapped_column(String(120), nullable=True)

    label_mode: Mapped[LabelMode] = mapped_column(
        enum_column(LabelMode, "label_mode", length=20),
        nullable=False,
        default=LabelMode.HIDDEN,
    )
    # So faz sentido com label_mode != HIDDEN. Separado do modo porque "pode
    # escolher" e "tem de escolher" sao decisoes diferentes: uma empresa pode
    # oferecer os rotulos sem obrigar quem so vai bater entrada normal.
    label_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    labels: Mapped[list["PunchLabel"]] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="PunchLabel.position",
    )

    def __repr__(self) -> str:
        return f"<PunchConfig note={self.note_mode} label={self.label_mode}>"


class PunchLabel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Uma opcao de rotulo cadastrada pelo RH.

    Cada opcao carrega o `entry_type`. E o que permite ao funcionario escolher
    "Inicio do almoco" sem precisar saber que aquilo conta como intervalo — a
    traducao fica com quem entende de jornada, que e o RH, e nao com quem esta
    com o celular na mao na porta do hangar.
    """

    __tablename__ = "punch_labels"
    __table_args__ = (
        # Dois rotulos com o mesmo nome tornariam o relatorio ambiguo.
        UniqueConstraint("tenant_id", "name", name="uq_punch_labels_tenant_name"),
    )

    config_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("punch_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(LABEL_MAX_LENGTH), nullable=False)
    entry_type: Mapped[EntryType] = mapped_column(
        enum_column(EntryType, "entry_type", length=20),
        nullable=False,
    )
    # Ordem de exibicao na tela do funcionario. O RH monta a sequencia do dia
    # (entrada, almoco, volta, saida) e ela vira a ordem dos botoes.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    config: Mapped[PunchConfig] = relationship(back_populates="labels")

    def __repr__(self) -> str:
        return f"<PunchLabel {self.name} -> {self.entry_type}>"
