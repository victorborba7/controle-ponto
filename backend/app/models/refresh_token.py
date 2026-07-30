"""RefreshToken — sessao de longa duracao, revogavel.

O access token e um JWT curto e sem estado: rapido de validar, mas impossivel
de revogar antes de expirar. O refresh token e o oposto — opaco e guardado
aqui, para que desligar um funcionario ou um aparelho roubado tenha efeito
imediato.

O token em si nunca e persistido, so o SHA-256 dele: vazar esta tabela nao
entrega sessao de ninguem.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import SubjectType


class RefreshToken(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_subject", "tenant_id", "subject_type", "subject_id"),
    )

    # SHA-256 e suficiente aqui (ao contrario de senha, que precisa de Argon2):
    # o token ja e 48 bytes aleatorios, entao nao ha o que forcar por dicionario.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Sem FK para users/employees: sao duas tabelas distintas e o dono varia
    # conforme subject_type. A validacao carrega o titular pelo tipo.
    subject_type: Mapped[SubjectType] = mapped_column(
        enum_column(SubjectType, "subject_type", length=20), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cadeia de rotacao: cada uso troca o token e aponta para o sucessor.
    # E o que permite detectar reuso de um token ja gasto (ver auth_service).
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    def is_usable(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<RefreshToken {self.subject_type}:{self.subject_id}>"
