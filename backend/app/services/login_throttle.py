"""Teto de tentativas de login.

Duas regras, porque uma so nao cobre os dois ataques que existem:

- **Por identidade** — cinco falhas na mesma conta dentro da janela e a conta
  para de aceitar tentativas. Pega quem escolhe uma matricula e testa senhas.
- **Por endereco** — dez identidades *diferentes* falhando do mesmo endereco na
  janela e o endereco para. Pega o oposto: uma senha provavel testada contra a
  empresa inteira, em que cada conta falha uma vez so e o teto por identidade
  nunca dispara.

A segunda regra conta **identidades distintas**, e nao tentativas, de proposito.
Um escritorio inteiro sai por um IP so, e contar tentativas bloquearia a empresa
numa segunda-feira de dedo errado. Ninguem erra a senha de dez colegas.

## O que a janela significa

Nao ha coluna de "bloqueado ate": o bloqueio e consequencia de haver falhas
demais nos ultimos N minutos, e some sozinho quando elas envelhecem. Tentativa
barrada **nao conta como falha nova** — senao quem tentasse de novo no minuto 14
empurraria o proprio desbloqueio para frente, e o legitimo (que erra e insiste)
seria punido mais que o atacante (que espera).

## Crescimento da tabela

Login bem-sucedido apaga as linhas da identidade, e uma falha fora da janela
reaproveita a linha zerando o contador. O numero de linhas fica limitado aos
pares (identidade, endereco) recentes, sem precisar de rotina de expurgo.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.login_attempt import IP_DESCONHECIDO, LoginAttempt


class Throttled(Exception):
    """Tentativas demais. `retry_after` e quando a janela expira, em segundos."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Bloqueado por mais {retry_after}s")

    @property
    def minutes(self) -> int:
        """Arredondado para cima, e nunca zero: "tente em 0 min" nao orienta."""
        return max(1, -(-self.retry_after // 60))


def identity_key(*, audience: str, tenant_slug: str, identifier: str) -> str:
    """Chave estavel da identidade tentada.

    Inclui o publico porque `admin` e `employee` sao tabelas e credenciais
    diferentes; inclui o slug porque a mesma matricula existe em cada empresa.
    Normalizada em minusculas para que variar a caixa nao crie um contador novo
    — que seria a forma mais barata de contornar o teto.
    """
    bruto = f"{audience}:{tenant_slug.strip().lower()}:{identifier.strip().lower()}"
    return hashlib.sha256(bruto.encode()).hexdigest()


async def ensure_allowed(session: AsyncSession, *, identity: str, ip: str | None) -> None:
    """Levanta `Throttled` se a identidade ou o endereco estiverem no teto.

    Chamada **antes** de conferir a senha: o ponto do teto e nao gastar um hash
    Argon2 por tentativa, e nao apenas recusar depois de gastar.
    """
    agora = datetime.now(UTC)
    janela = agora - timedelta(seconds=settings.login_failure_window_seconds)

    ultima = await _identity_blocked_since(session, identity, janela)
    if ultima is None and ip:
        ultima = await _ip_blocked_since(session, ip, janela)

    if ultima is None:
        return

    expira = ultima + timedelta(seconds=settings.login_failure_window_seconds)
    raise Throttled(max(1, int((expira - agora).total_seconds())))


async def record_failure(session: AsyncSession, *, identity: str, ip: str | None) -> None:
    """Contabiliza uma tentativa malsucedida.

    Quem chama precisa **commitar** antes de devolver o erro: a dependencia de
    sessao desfaz a transacao quando o endpoint levanta excecao, e a falha
    sumiria junto com a resposta 401 que ela deveria estar contando.
    """
    agora = datetime.now(UTC)
    janela = agora - timedelta(seconds=settings.login_failure_window_seconds)
    endereco = ip or IP_DESCONHECIDO

    linha = await session.scalar(
        select(LoginAttempt).where(
            LoginAttempt.identity_hash == identity,
            LoginAttempt.ip_address == endereco,
        )
    )

    if linha is None:
        session.add(
            LoginAttempt(
                identity_hash=identity,
                ip_address=endereco,
                failures=1,
                first_failure_at=agora,
                last_failure_at=agora,
            )
        )
        return

    if linha.last_failure_at < janela:
        # A serie anterior ja envelheceu: comeca uma nova, em vez de somar a
        # tentativa de hoje com a de ontem.
        linha.failures = 1
        linha.first_failure_at = agora
    else:
        linha.failures += 1

    linha.last_failure_at = agora


async def clear(session: AsyncSession, *, identity: str) -> None:
    """Zera o contador da identidade apos autenticacao bem-sucedida.

    Apaga as linhas de todos os enderecos, e nao so a do atual: quem provou ser
    o titular nao deve continuar a um erro de distancia do bloqueio por causa de
    tentativas feitas de outra rede.
    """
    await session.execute(delete(LoginAttempt).where(LoginAttempt.identity_hash == identity))


# --------------------------------------------------------------------------
# As duas regras
# --------------------------------------------------------------------------


async def _identity_blocked_since(
    session: AsyncSession, identity: str, janela: datetime
) -> datetime | None:
    """Falha mais recente da identidade, se ela ja passou do teto.

    Soma as linhas em vez de olhar uma so: trocar de rede a cada tentativa
    espalharia as falhas por varias linhas, e o contador por linha nunca
    chegaria ao teto.
    """
    resultado = await session.execute(
        select(
            func.coalesce(func.sum(LoginAttempt.failures), 0),
            func.max(LoginAttempt.last_failure_at),
        ).where(
            LoginAttempt.identity_hash == identity,
            LoginAttempt.last_failure_at >= janela,
        )
    )
    total, ultima = resultado.one()

    if total < settings.login_max_failures:
        return None
    return ultima


async def _ip_blocked_since(session: AsyncSession, ip: str, janela: datetime) -> datetime | None:
    """Falha mais recente do endereco, se ele ja errou identidades demais."""
    resultado = await session.execute(
        select(
            func.count(func.distinct(LoginAttempt.identity_hash)),
            func.max(LoginAttempt.last_failure_at),
        ).where(
            LoginAttempt.ip_address == ip,
            LoginAttempt.ip_address != IP_DESCONHECIDO,
            LoginAttempt.last_failure_at >= janela,
        )
    )
    identidades, ultima = resultado.one()

    if identidades < settings.login_spray_max_identities:
        return None
    return ultima
