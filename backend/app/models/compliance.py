"""Tabelas de conformidade: consentimento LGPD e trilha de auditoria.

Existem desde a Etapa 1 porque consentimento precisa ser registrado no mesmo
ato do cadastro biometrico (Etapa 4) — nao da para adicionar retroativamente
sem invalidar o que ja foi coletado.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import AuditAction, ConsentType


class Consent(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Consentimento do funcionario para o tratamento de biometria e localizacao.

    Biometria e localizacao sao consentidas em registros separados: sao
    finalidades distintas e a LGPD exige consentimento especifico por
    finalidade. Revogar um nao revoga o outro.
    """

    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_tenant_employee", "tenant_id", "employee_id", "consent_type"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        enum_column(ConsentType, "consent_type", length=20),
        nullable=False,
    )
    # Versao do texto aceito. Mudou o termo, precisa de novo aceite — sem isto
    # nao da para provar *o que* a pessoa concordou.
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Evidencia de onde o aceite partiu.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return f"<Consent {self.consent_type} employee={self.employee_id}>"


class AuditLog(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Trilha de auditoria — append-only.

    Sem updated_at de proposito: registro de auditoria nao se altera. Sem FK
    para o ator tambem de proposito: se o usuario for excluido (direito ao
    esquecimento), a trilha do que ele fez precisa sobreviver.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # "user", "employee" ou "system"; id solto, sem FK (ver docstring).
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    action: Mapped[AuditAction] = mapped_column(
        enum_column(AuditAction, "audit_action", length=30),
        nullable=False,
    )
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    # Contexto do evento. NUNCA guardar aqui imagem, embedding ou senha.
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}>"
