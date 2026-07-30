"""Registro da trilha de auditoria.

Centralizado num helper porque auditoria esquecida e auditoria inexistente:
com uma unica funcao, cada ponto do sistema que decide algo relevante grava do
mesmo jeito, com os mesmos campos.

**Nunca passar imagem, embedding ou senha no payload.** A trilha e consultada
por gente do RH e sobrevive ao expurgo dos dados originais.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import Principal
from app.models import AuditLog
from app.models.enums import AuditAction

SYSTEM_ACTOR = "system"


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    description: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Grava um evento na trilha.

    Nao faz commit: o evento participa da mesma transacao da acao que o gerou,
    entao uma operacao revertida nao deixa registro de auditoria mentindo que
    aconteceu.
    """
    entry = AuditLog(
        tenant_id=tenant_id,
        created_at=datetime.now(UTC),
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        description=description,
        ip_address=ip_address,
    )
    session.add(entry)
    return entry


async def record_for(
    session: AsyncSession,
    principal: Principal,
    *,
    action: AuditAction,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    description: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Atalho para quando o autor da acao e quem esta autenticado."""
    return await record(
        session,
        tenant_id=principal.tenant_id,
        action=action,
        actor_type=principal.subject_type.value,
        actor_id=principal.subject_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        description=description,
        ip_address=ip_address,
    )
