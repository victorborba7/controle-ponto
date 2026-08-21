"""O "dia" de um funcionario, no fuso da empresa.

Ate aqui o sistema nao tinha esse conceito. `tenants.timezone` e
`sites.timezone` existiam e ninguem lia: toda consulta trabalhava em UTC, e
"hoje" era o dia UTC.

Isso passa despercebido no Brasil (UTC-3, virada a 21h) e quebra na Florida
(UTC-4 no horario de verao): uma batida as 20h de terca em Miami e
quarta-feira em UTC. O relatorio poria a jornada no dia seguinte, e a soma de
horas de terca sairia menor do que foi trabalhado.

**O fuso vem do tenant, nao do site.** Segue a decisao D10 — jornada e politica
da empresa, e um funcionario que circula entre o hangar e o escritorio nao pode
ter dois "dias" diferentes conforme onde bateu o ponto. `sites.timezone`
continua existindo para exibicao local, nao para apuracao.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Usado quando o tenant tem fuso invalido gravado. Nao inventa horario local:
#: em UTC a data e no minimo estavel e explicavel, e um fuso quebrado e defeito
#: de cadastro que precisa aparecer, nao ser mascarado com um palpite.
FUSO_DE_EMERGENCIA = "UTC"


def zona(fuso: str | None) -> ZoneInfo:
    """Resolve o fuso do tenant, tolerando cadastro invalido."""
    try:
        return ZoneInfo(fuso or FUSO_DE_EMERGENCIA)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(FUSO_DE_EMERGENCIA)


def dia_local(instante: datetime, fuso: str | None) -> date:
    """A que dia de trabalho um instante pertence.

    Aceita datetime ingenuo tratando-o como UTC: e o que vem do banco em
    colunas gravadas antes de `DateTime(timezone=True)` existir, e presumir
    horario local ali produziria uma data errada em silencio.
    """
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=UTC)
    return instante.astimezone(zona(fuso)).date()


def inicio_do_dia(dia: date, fuso: str | None) -> datetime:
    """Instante UTC em que o dia local comeca.

    Existe para consultas por intervalo: comparar `recorded_at` com limites em
    UTC preserva o indice, enquanto converter a coluna dentro do WHERE o
    descartaria.
    """
    return datetime.combine(dia, datetime.min.time(), tzinfo=zona(fuso)).astimezone(UTC)
