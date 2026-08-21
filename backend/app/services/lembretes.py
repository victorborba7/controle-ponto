"""Quem precisa ser lembrado de registrar a atividade, e quando.

A regra: a cada hora cheia depois da entrada, enquanto o dia estiver aberto.
Fecha no `OUT` e nao volta — a nao ser que o funcionario reabra o dia batendo
de novo, e ai os lembretes voltam junto, porque ele voltou a trabalhar.

**Nao ha reposicao de lembrete perdido.** Se a maquina ficou fora do ar das 9h
as 11h, ninguem recebe "voce perdeu os lembretes das 9h e das 10h" ao voltar:
so o da hora corrente sai. Tres notificacoes de uma vez seriam ruido sobre um
problema que ja passou.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import IDIOMA_PADRAO, Msg, traduzir
from app.models import Device, Employee, PunchReminder, Tenant, TimeEntry
from app.models.enums import EntryType
from app.services import notificacoes
from app.services.calendario import dia_local

logger = logging.getLogger(__name__)

#: Teto de lembretes por dia. Doze horas depois da entrada, quem nao bateu
#: saida nao esqueceu — ou esqueceu de um jeito que notificacao nao resolve, e
#: insistir a noite inteira so ensina a ignorar o app.
MAXIMO_DE_LEMBRETES = 12


@dataclass
class Jornada:
    """Um dia aberto de um funcionario."""

    employee: Employee
    tenant_id: object
    dia: date
    entrada_em: datetime


async def jornadas_abertas(session: AsyncSession, agora: datetime) -> list[Jornada]:
    """Funcionarios que entraram hoje e ainda nao encerraram o dia.

    Percorre tenant a tenant porque "hoje" depende do fuso de cada empresa —
    no mesmo instante, uma pode estar em 21/08 e outra em 22/08.
    """
    abertas: list[Jornada] = []

    tenants = (await session.scalars(select(Tenant).where(Tenant.is_active.is_(True)))).all()

    for tenant in tenants:
        dia = dia_local(agora, tenant.timezone)

        entradas = (
            await session.scalars(
                select(TimeEntry)
                .where(
                    TimeEntry.tenant_id == tenant.id,
                    TimeEntry.business_date == dia,
                )
                .order_by(TimeEntry.recorded_at)
            )
        ).all()

        por_funcionario: dict[object, list[TimeEntry]] = {}
        for entrada in entradas:
            por_funcionario.setdefault(entrada.employee_id, []).append(entrada)

        for employee_id, batidas in por_funcionario.items():
            # Dia aberto = a ultima batida nao foi saida. Cobre a reabertura de
            # graca: quem bateu saida e voltou tem a intermediaria como ultima,
            # e volta a ser lembrado — porque voltou a trabalhar.
            if batidas[-1].entry_type is EntryType.OUT:
                continue

            primeira_entrada = next(
                (b for b in batidas if b.entry_type is EntryType.IN), None
            )
            if primeira_entrada is None:
                continue

            employee = await session.get(Employee, employee_id)
            if employee is None:
                continue

            abertas.append(
                Jornada(
                    employee=employee,
                    tenant_id=tenant.id,
                    dia=dia,
                    entrada_em=primeira_entrada.recorded_at,
                )
            )

    return abertas


def hora_devida(jornada: Jornada, agora: datetime) -> int | None:
    """Qual lembrete e o desta hora, ou None se ainda nao ha um."""
    entrada = jornada.entrada_em
    if entrada.tzinfo is None:
        entrada = entrada.replace(tzinfo=UTC)

    horas = int((agora - entrada).total_seconds() // 3600)
    if horas < 1 or horas > MAXIMO_DE_LEMBRETES:
        return None
    return horas


async def executar(session: AsyncSession, agora: datetime | None = None) -> int:
    """Envia os lembretes devidos agora. Devolve quantos sairam.

    Idempotente por construcao: a linha em `punch_reminders` e gravada antes do
    envio, e a restricao unica derruba a segunda tentativa da mesma hora. Duas
    execucoes simultaneas do agendador nao geram duas notificacoes.
    """
    agora = agora or datetime.now(UTC)
    enviados = 0

    for jornada in await jornadas_abertas(session, agora):
        hora = hora_devida(jornada, agora)
        if hora is None:
            continue

        if not await _marcar(session, jornada, hora, agora):
            continue  # ja foi lembrado nesta hora

        tokens = await _tokens_do_funcionario(session, jornada.employee)
        if not tokens:
            continue

        resultado = await notificacoes.enviar(
            [
                notificacoes.Mensagem(
                    token=token,
                    titulo=traduzir(Msg.LEMBRETE_TITULO, IDIOMA_PADRAO),
                    corpo=traduzir(Msg.LEMBRETE_CORPO, IDIOMA_PADRAO, horas=hora),
                )
                for token in tokens
            ]
        )
        enviados += resultado.enviadas

        await _limpar_tokens_mortos(session, resultado.tokens_mortos)

    return enviados


async def _marcar(
    session: AsyncSession, jornada: Jornada, hora: int, agora: datetime
) -> bool:
    """Reserva a hora. False se outra execucao ja tinha reservado."""
    session.add(
        PunchReminder(
            tenant_id=jornada.tenant_id,
            employee_id=jornada.employee.id,
            business_date=jornada.dia,
            hour_index=hora,
            sent_at=agora,
        )
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def _tokens_do_funcionario(session: AsyncSession, employee: Employee) -> list[str]:
    devices = (
        await session.scalars(
            select(Device).where(
                Device.employee_id == employee.id,
                Device.revoked_at.is_(None),
                Device.push_token.is_not(None),
            )
        )
    ).all()
    return [d.push_token for d in devices if notificacoes.token_valido(d.push_token)]


async def _limpar_tokens_mortos(session: AsyncSession, tokens: list[str]) -> None:
    """Apaga token que o Expo declarou invalido, para nao retentar sempre."""
    if not tokens:
        return

    devices = (
        await session.scalars(select(Device).where(Device.push_token.in_(tokens)))
    ).all()
    for device in devices:
        device.push_token = None
    await session.flush()
