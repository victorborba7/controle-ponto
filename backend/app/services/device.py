"""Aparelhos pareados: consulta, revogacao e reautorizacao pelo RH.

O pareamento e o que impede uma credencial vazada de bater ponto de qualquer
celular (ver `_ensure_device_trusted`). Ele so vale alguma coisa se houver como
**cortar** um aparelho — celular roubado, funcionario desligado que devolveu o
aparelho, aparelho de terceiro usado uma vez e nunca mais.

Revogar nao apaga: o historico de pontos aponta para o `device_id`, e um ponto
contestado precisa continuar dizendo de qual aparelho veio.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantRepository
from app.models import Device, Employee, RefreshToken


async def list_for_employee(repo: TenantRepository, employee: Employee) -> list[Device]:
    """Aparelhos do funcionario, o de uso mais recente primeiro."""
    result = await repo.session.execute(
        repo.query(Device)
        .where(Device.employee_id == employee.id)
        .order_by(desc(Device.last_seen_at))
    )
    return list(result.scalars().all())


async def revoke(session: AsyncSession, repo: TenantRepository, device: Device) -> Device:
    """Corta o aparelho e encerra as sessoes abertas nele.

    Os dois passos sao necessarios e resolvem coisas diferentes: marcar
    `revoked_at` barra a proxima batida, e revogar os refresh tokens impede que
    a sessao ja aberta continue navegando por ate 30 dias. Sem o segundo, quem
    esta com o aparelho continuaria lendo o historico do funcionario.

    Idempotente: revogar o que ja estava revogado nao mexe na data original,
    que e o que o RH usa para saber desde quando o aparelho esta fora.
    """
    if device.revoked_at is None:
        device.revoked_at = datetime.now(UTC)

    await _revoke_sessions(session, repo.tenant_id, device.id)
    await repo.flush()
    return device


async def authorize(repo: TenantRepository, device: Device) -> Device:
    """Reabilita um aparelho revogado.

    Existe como ato explicito do RH justamente porque deixou de acontecer
    sozinho: um login bem-sucedido reabilitava o aparelho, e assim revogar um
    celular roubado durava ate quem estivesse com ele digitar a senha.

    Nao emite sessao nenhuma — o funcionario entra de novo pelo app.
    """
    device.revoked_at = None
    await repo.flush()
    return device


async def _revoke_sessions(
    session: AsyncSession, tenant_id: uuid.UUID, device_id: uuid.UUID
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.device_id == device_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
