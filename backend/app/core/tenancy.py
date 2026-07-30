"""Identidade autenticada e escopo de tenant.

O `Principal` e a unica fonte de verdade sobre quem esta chamando e a que
empresa pertence. Ele so e construido a partir de um JWT com assinatura
valida — nunca de cabecalho, query string ou corpo da requisicao, que o
cliente controla.
"""

import uuid
from dataclasses import dataclass

from app.models.enums import SubjectType, UserRole


@dataclass(frozen=True)
class Principal:
    """Quem esta autenticado nesta requisicao.

    Imutavel de proposito: nenhuma camada acima pode trocar o tenant no meio
    do caminho.
    """

    subject_id: uuid.UUID
    subject_type: SubjectType
    tenant_id: uuid.UUID
    role: UserRole | None = None
    device_id: uuid.UUID | None = None

    @property
    def is_admin(self) -> bool:
        return self.subject_type is SubjectType.USER

    @property
    def is_employee(self) -> bool:
        return self.subject_type is SubjectType.EMPLOYEE

    def has_role(self, *roles: UserRole) -> bool:
        return self.role is not None and self.role in roles


def principal_from_claims(claims: dict) -> Principal | None:
    """Converte as claims de um JWT ja validado em Principal.

    Retorna None se as claims nao formarem uma identidade coerente. Um token
    assinado mas malformado (tenant que nao e UUID, papel inexistente) e
    tratado como token invalido, nao como erro do servidor.
    """
    try:
        subject_type = SubjectType(claims["styp"])
        subject_id = uuid.UUID(claims["sub"])
        tenant_id = uuid.UUID(claims["tid"])
    except (KeyError, ValueError):
        return None

    role: UserRole | None = None
    if raw_role := claims.get("role"):
        try:
            role = UserRole(raw_role)
        except ValueError:
            return None

    device_id: uuid.UUID | None = None
    if raw_device := claims.get("did"):
        try:
            device_id = uuid.UUID(raw_device)
        except ValueError:
            return None

    return Principal(
        subject_id=subject_id,
        subject_type=subject_type,
        tenant_id=tenant_id,
        role=role,
        device_id=device_id,
    )
