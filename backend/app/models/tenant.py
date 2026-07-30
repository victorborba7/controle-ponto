"""Tenant — a empresa cliente.

O MVP serve uma empresa so, mas a tabela existe desde ja: e a raiz de todo o
isolamento de dados e adiciona-la depois exigiria reescrever cada consulta.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Identificador curto e estavel, usado no login do app ("codigo da empresa")
    # e no subdominio quando o produto virar self-service.
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Sao_Paulo")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
