"""FaceTemplate — o embedding facial de referencia de um funcionario.

Tabela mais sensivel do sistema: o embedding e dado biometrico, que a LGPD
classifica como dado pessoal sensivel. Nunca sai por endpoint nenhum.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# ArcFace (buffalo_l) produz vetores de 512 dimensoes. Se o modelo mudar, a
# dimensao muda junto — por isso model_name/model_version sao gravados em cada
# linha: permite conviver com duas geracoes durante uma remigracao.
EMBEDDING_DIM = 512


class FaceTemplate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "face_templates"
    __table_args__ = (
        # Busca tipica: templates ativos de um funcionario deste tenant.
        Index("ix_face_templates_tenant_employee", "tenant_id", "employee_id", "is_active"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    model_name: Mapped[str] = mapped_column(String(60), nullable=False)
    model_version: Mapped[str] = mapped_column(String(30), nullable=False)

    # Score de qualidade da foto de origem (nitidez, frontalidade, tamanho do
    # rosto). Serve para descartar templates ruins e explicar match fraco.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Chave opaca no storage. A imagem original fica criptografada em repouso e
    # so e acessivel por rotina interna — nunca por URL publica.
    source_image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Desativacao em vez de delete: manter o rastro de quais templates estavam
    # valendo quando cada ponto foi aprovado (auditoria).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<FaceTemplate employee={self.employee_id} model={self.model_name}>"
