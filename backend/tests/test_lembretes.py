"""Lembrete horario: quem recebe, quando para, e por que nao duplica.

O agendador roda no processo da API, numa maquina so, e toda implantacao a
reinicia. O que impede um reinicio as 9h05 de reenviar o lembrete das 9h e a
tabela `punch_reminders` — e e ela que estes testes protegem.

O envio em si (`notificacoes.enviar`) e substituido: exercitar o servico do
Expo aqui testaria a rede da Anthropic, nao esta regra.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, PunchReminder, TimeEntry
from app.models.enums import DevicePlatform, EntryType
from app.services import lembretes, notificacoes
from app.services.calendario import dia_local
from tests.conftest import create_employee, create_tenant

TOKEN = "ExponentPushToken[teste-do-hangar]"


@pytest.fixture
def push_capturado(monkeypatch) -> list[notificacoes.Mensagem]:
    """Intercepta o envio e devolve o que teria ido para o Expo."""
    capturadas: list[notificacoes.Mensagem] = []

    async def _falso(mensagens):
        capturadas.extend(mensagens)
        return notificacoes.ResultadoEnvio(enviadas=len(mensagens))

    monkeypatch.setattr(notificacoes, "enviar", _falso)
    return capturadas


@pytest.fixture
async def jornada(db: AsyncSession) -> dict:
    """Funcionario que entrou ha 3 horas e nao encerrou o dia."""
    tenant = await create_tenant(db, slug="acme")
    funcionario = await create_employee(db, tenant, external_code="0001")
    await db.flush()

    db.add(
        Device(
            tenant_id=tenant.id,
            employee_id=funcionario.id,
            device_fingerprint="celular",
            platform=DevicePlatform.ANDROID,
            push_token=TOKEN,
        )
    )

    agora = datetime.now(UTC)
    entrada_em = agora - timedelta(hours=3)
    db.add(
        TimeEntry(
            tenant_id=tenant.id,
            employee_id=funcionario.id,
            entry_type=EntryType.IN,
            recorded_at=entrada_em,
            business_date=dia_local(entrada_em, tenant.timezone),
        )
    )
    await db.commit()

    return {
        "tenant": tenant,
        "funcionario": funcionario,
        "funcionario_id": funcionario.id,
        "agora": agora,
        "entrada_em": entrada_em,
    }


async def _bater(db: AsyncSession, jornada: dict, tipo: EntryType, *, quando: datetime):
    db.add(
        TimeEntry(
            tenant_id=jornada["tenant"].id,
            employee_id=jornada["funcionario_id"],
            entry_type=tipo,
            recorded_at=quando,
            business_date=dia_local(quando, jornada["tenant"].timezone),
        )
    )
    await db.commit()


# --------------------------------------------------------------------------
# Envio
# --------------------------------------------------------------------------


async def test_lembra_quem_entrou_e_nao_saiu(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    enviados = await lembretes.executar(db, jornada["agora"])
    await db.commit()

    assert enviados == 1
    assert push_capturado[0].token == TOKEN
    assert "3" in push_capturado[0].corpo


async def test_nao_lembra_antes_da_primeira_hora(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    """Quem acabou de entrar nao precisa ser lembrado de que entrou."""
    logo_apos = jornada["entrada_em"] + timedelta(minutes=45)

    assert await lembretes.executar(db, logo_apos) == 0
    assert push_capturado == []


async def test_para_de_lembrar_apos_a_saida(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    await _bater(db, jornada, EntryType.OUT, quando=jornada["agora"] - timedelta(minutes=5))

    assert await lembretes.executar(db, jornada["agora"]) == 0
    assert push_capturado == []


async def test_dia_reaberto_volta_a_lembrar(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    """Quem bateu saida e voltou esta trabalhando de novo."""
    await _bater(db, jornada, EntryType.OUT, quando=jornada["agora"] - timedelta(hours=1))
    await _bater(
        db, jornada, EntryType.INTERMEDIATE, quando=jornada["agora"] - timedelta(minutes=10)
    )

    assert await lembretes.executar(db, jornada["agora"]) == 1


async def test_teto_de_lembretes_por_dia(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    """Depois de 12 horas, insistir so ensina a ignorar o app."""
    muito_depois = jornada["entrada_em"] + timedelta(hours=lembretes.MAXIMO_DE_LEMBRETES + 1)

    assert await lembretes.executar(db, muito_depois) == 0


async def test_funcionario_sem_token_nao_quebra_a_rodada(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    devices = (await db.scalars(select(Device))).all()
    for device in devices:
        device.push_token = None
    await db.commit()

    assert await lembretes.executar(db, jornada["agora"]) == 0


# --------------------------------------------------------------------------
# Idempotencia — o motivo da tabela existir
# --------------------------------------------------------------------------


async def test_duas_rodadas_na_mesma_hora_lembram_uma_vez(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    """O caso do reinicio: implantacao as 9h05 nao reenvia o lembrete das 9h."""
    await lembretes.executar(db, jornada["agora"])
    await db.commit()

    segunda = await lembretes.executar(db, jornada["agora"] + timedelta(minutes=5))
    await db.commit()

    assert segunda == 0
    assert len(push_capturado) == 1


async def test_hora_seguinte_lembra_de_novo(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    await lembretes.executar(db, jornada["agora"])
    await db.commit()

    await lembretes.executar(db, jornada["agora"] + timedelta(hours=1))
    await db.commit()

    assert len(push_capturado) == 2
    horas = [r.hour_index for r in (await db.scalars(select(PunchReminder))).all()]
    assert sorted(horas) == [3, 4]


async def test_hora_perdida_nao_e_reposta(
    db: AsyncSession, jornada: dict, push_capturado: list
):
    """Maquina fora do ar das 9h as 11h nao gera tres notificacoes ao voltar.

    So o lembrete da hora corrente sai — repetir o que passou seria ruido sobre
    um problema que ja acabou.
    """
    await lembretes.executar(db, jornada["entrada_em"] + timedelta(hours=6))
    await db.commit()

    horas = [r.hour_index for r in (await db.scalars(select(PunchReminder))).all()]
    assert horas == [6]


# --------------------------------------------------------------------------
# Token invalido
# --------------------------------------------------------------------------


async def test_token_morto_e_apagado(db: AsyncSession, jornada: dict, monkeypatch):
    """Sem apagar, o mesmo token invalido seria retentado para sempre."""

    async def _recusa(mensagens):
        return notificacoes.ResultadoEnvio(
            enviadas=0, tokens_mortos=[m.token for m in mensagens]
        )

    monkeypatch.setattr(notificacoes, "enviar", _recusa)

    await lembretes.executar(db, jornada["agora"])
    await db.commit()

    device = (await db.scalars(select(Device))).first()
    assert device.push_token is None


def test_formato_do_token_e_conferido_antes_de_enviar():
    assert notificacoes.token_valido(TOKEN)
    assert not notificacoes.token_valido("qualquer-coisa")
    assert not notificacoes.token_valido(None)
