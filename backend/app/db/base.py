"""Base declarativa e mixins compartilhados por todos os modelos."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    """Chave primaria UUID.

    UUID em vez de serial porque na fase SaaS os ids circulam entre servicos e
    aparecem em URLs — sequencial vazaria volume de dados e permitiria enumerar
    registros de outros tenants.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """created_at / updated_at preenchidos pelo banco."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Vinculo obrigatorio com a empresa dona do registro.

    Toda tabela de negocio herda isto. O valor vem sempre do JWT, nunca de
    parametro de request — ver a dependencia CurrentTenant na Etapa 2.

    ondelete="CASCADE": remover um tenant remove tudo dele, requisito de
    portabilidade/exclusao da LGPD (Etapa 11).
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
