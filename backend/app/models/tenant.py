"""Tenant — a empresa cliente.

O MVP serve uma empresa so, mas a tabela existe desde ja: e a raiz de todo o
isolamento de dados e adiciona-la depois exigiria reescrever cada consulta.
"""

from sqlalchemy import Boolean, Float, String
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

    # Limiares de reconhecimento facial. NULL = usa o padrao global de
    # `settings`, que e o caso de toda empresa real.
    #
    # Existem porque o limiar certo depende da populacao e da operacao: um
    # hangar com iluminacao ruim e equipe usando oculos de protecao tolera
    # menos rigor que um escritorio. Sao entregavel previsto da Etapa 10.
    #
    # O primeiro uso, porem, e outro: o tenant de demonstracao submetido a
    # revisao da Apple. O revisor nao tem rosto cadastrado, e sem afrouxar o
    # limiar dele a batida vira NO_MATCH -> REJECTED, que e "nao conseguimos
    # exercitar a funcionalidade principal" e reprova o build.
    #
    # ATENCAO: valor baixo aceita qualquer rosto. So faz sentido em tenant sem
    # gente de verdade dentro.
    face_match_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_review_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
