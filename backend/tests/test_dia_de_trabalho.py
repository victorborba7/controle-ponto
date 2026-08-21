"""O dia de trabalho: entrada automatica, saida declarada e fuso da empresa.

Antes destas regras o sistema alternava entrada/saida pela ultima batida
absoluta, sem conceito de dia. Dois defeitos vinham dai, e cada um tem teste
aqui:

1. Quem esquecia de bater a saida na sexta tinha a primeira batida de segunda
   classificada como *saida* — uma jornada inteira invertida.
2. Quem so ia ao almoco tinha o dia encerrado sem ter pedido.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import Msg, traduzir
from app.models import TimeEntry
from app.models.enums import EntryType
from app.services.calendario import dia_local
from tests.conftest import bater_ponto


async def _envelhecer(db: AsyncSession, *, horas: float) -> TimeEntry:
    """Recua a ultima batida no tempo, para escapar do teto de batida repetida."""
    entry = (
        await db.scalars(select(TimeEntry).order_by(TimeEntry.recorded_at.desc()))
    ).first()
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=horas)
    await db.commit()
    return entry


# --------------------------------------------------------------------------
# Entrada automatica
# --------------------------------------------------------------------------


async def test_primeira_batida_do_dia_e_entrada(client: AsyncClient, cenario: dict):
    resposta = await bater_ponto(client, cenario)
    assert resposta.json()["entry"]["entry_type"] == "in"


async def test_primeira_do_dia_e_entrada_mesmo_apos_dia_sem_saida(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """O defeito que motivou a mudanca.

    Sexta com entrada e sem saida; na segunda a primeira batida tem de ser
    entrada. Pela alternancia antiga ela viria como saida, porque a ultima
    batida existente era uma entrada.
    """
    await bater_ponto(client, cenario)

    # Empurra a batida para tres dias atras, e o dia junto: ela deixa de ser
    # "hoje" sem deixar de existir.
    entry = await _envelhecer(db, horas=72)
    entry.business_date = dia_local(entry.recorded_at, "UTC")
    await db.commit()

    hoje = await bater_ponto(client, cenario)
    assert hoje.json()["entry"]["entry_type"] == "in"


# --------------------------------------------------------------------------
# Saida declarada
# --------------------------------------------------------------------------


async def test_saida_sem_entrada_no_dia_e_recusada(client: AsyncClient, cenario: dict):
    resposta = await bater_ponto(client, cenario, closes_day=True)

    assert resposta.status_code == 422
    assert resposta.json()["detail"] == traduzir(Msg.SAIDA_SEM_ENTRADA, "en")


async def test_saida_sem_entrada_nao_grava_nada(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Recusar com 422 nao basta se a batida ja tiver sido gravada."""
    await bater_ponto(client, cenario, closes_day=True)

    registros = (await db.scalars(select(TimeEntry))).all()
    assert registros == []


async def test_saida_declarada_encerra_o_dia(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)
    await _envelhecer(db, horas=8)

    saida = await bater_ponto(client, cenario, closes_day=True)
    assert saida.json()["entry"]["entry_type"] == "out"


# --------------------------------------------------------------------------
# Reabertura (decisao: bater depois da saida reabre o dia)
# --------------------------------------------------------------------------


async def test_batida_apos_a_saida_reabre_o_dia(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Bloquear seria pior que registrar: e o principio da decisao D5.

    O caso real e comum — a pessoa marcou saida achando que ia embora, e
    voltou. Recusar deixaria o periodo da tarde sem registro nenhum.
    """
    await bater_ponto(client, cenario)
    await _envelhecer(db, horas=8)
    await bater_ponto(client, cenario, closes_day=True)
    await _envelhecer(db, horas=4)

    volta = await bater_ponto(client, cenario)

    assert volta.status_code == 201
    assert volta.json()["entry"]["entry_type"] == "intermediate"


async def test_dia_reaberto_pode_ser_encerrado_de_novo(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)
    await _envelhecer(db, horas=8)
    await bater_ponto(client, cenario, closes_day=True)
    await _envelhecer(db, horas=4)
    await bater_ponto(client, cenario)
    await _envelhecer(db, horas=2)

    segunda_saida = await bater_ponto(client, cenario, closes_day=True)
    assert segunda_saida.json()["entry"]["entry_type"] == "out"


# --------------------------------------------------------------------------
# Fuso da empresa
# --------------------------------------------------------------------------


async def test_batida_recebe_o_dia_da_empresa(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)

    entry = await db.scalar(select(TimeEntry))
    tenant = cenario["tenant"]
    assert entry.business_date == dia_local(entry.recorded_at, tenant.timezone)


@pytest.mark.parametrize(
    ("fuso", "instante", "dia_esperado"),
    [
        # 20h de terca em Nova York ja e quarta em UTC. Pelo dia UTC a jornada
        # de terca sairia menor do que foi trabalhada.
        ("America/New_York", "2026-03-10T23:30:00+00:00", "2026-03-10"),
        # Mesma hora, do outro lado da virada local.
        ("America/New_York", "2026-03-11T05:30:00+00:00", "2026-03-11"),
        ("America/Sao_Paulo", "2026-03-11T02:30:00+00:00", "2026-03-10"),
        ("UTC", "2026-03-11T02:30:00+00:00", "2026-03-11"),
    ],
)
def test_dia_local_respeita_o_fuso(fuso: str, instante: str, dia_esperado: str):
    assert str(dia_local(datetime.fromisoformat(instante), fuso)) == dia_esperado


def test_fuso_invalido_nao_derruba_a_batida():
    """Cadastro quebrado vira dia UTC, nao excecao.

    Recusar a batida puniria o funcionario por um erro de cadastro do RH.
    """
    instante = datetime(2026, 3, 11, 2, 30, tzinfo=UTC)
    assert str(dia_local(instante, "Fuso/Inexistente")) == "2026-03-11"


def test_tipo_intermediario_existe_e_nao_e_intervalo():
    """INTERMEDIATE nao pode ser confundido com BREAK_END no relatorio."""
    assert EntryType.INTERMEDIATE.value == "intermediate"
    assert EntryType.INTERMEDIATE is not EntryType.BREAK_END
