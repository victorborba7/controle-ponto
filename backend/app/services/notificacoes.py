"""Envio de notificacao push, via Expo Push Service.

O app e Expo, entao o caminho e o servico de push do proprio Expo: ele fala com
APNs e FCM e devolve um resultado por mensagem. Isso evita guardar credenciais
de duas plataformas no backend — as chaves ficam no EAS.

**O envio nunca derruba quem chamou.** Um lembrete e conveniencia; falhar o
envio nao pode interromper o agendador nem, muito menos, uma batida. Toda falha
vira log e segue.
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

#: O Expo aceita ate 100 mensagens por chamada.
LOTE_MAXIMO = 100

TIMEOUT_SEGUNDOS = 10.0

#: Resposta do Expo para token que nao existe mais — app desinstalado, ou
#: aparelho restaurado. E o unico erro que exige acao nossa: apagar o token,
#: senao ele e retentado para sempre.
ERRO_TOKEN_MORTO = "DeviceNotRegistered"


@dataclass(frozen=True)
class Mensagem:
    token: str
    titulo: str
    corpo: str


@dataclass
class ResultadoEnvio:
    enviadas: int = 0
    #: Tokens que o Expo declarou invalidos. Quem chamou deve apaga-los.
    tokens_mortos: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.tokens_mortos is None:
            self.tokens_mortos = []


def token_valido(token: str | None) -> bool:
    """Formato do token do Expo, conferido antes de gastar uma chamada."""
    if not token:
        return False
    return token.startswith(("ExponentPushToken[", "ExpoPushToken["))


async def enviar(mensagens: list[Mensagem]) -> ResultadoEnvio:
    """Entrega as mensagens e devolve o que falhou de forma acionavel."""
    resultado = ResultadoEnvio()
    validas = [m for m in mensagens if token_valido(m.token)]
    if not validas:
        return resultado

    async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
        for inicio in range(0, len(validas), LOTE_MAXIMO):
            lote = validas[inicio : inicio + LOTE_MAXIMO]
            await _enviar_lote(cliente, lote, resultado)

    return resultado


async def _enviar_lote(
    cliente: httpx.AsyncClient, lote: list[Mensagem], resultado: ResultadoEnvio
) -> None:
    payload = [
        {
            "to": m.token,
            "title": m.titulo,
            "body": m.corpo,
            # `default` toca som e mostra badge; sem isto o lembrete chega mudo
            # no iPhone, e um lembrete que ninguem percebe nao lembra nada.
            "sound": "default",
            "priority": "high",
        }
        for m in lote
    ]

    try:
        resposta = await cliente.post(EXPO_PUSH_URL, json=payload)
        resposta.raise_for_status()
        tickets = resposta.json().get("data", [])
    except Exception:
        # Rede instavel, Expo fora do ar, resposta inesperada: nada disso pode
        # derrubar o agendador. O lembrete desta hora se perde, e o da proxima
        # sai normalmente.
        logger.exception("Falha ao enviar lote de push (%d mensagens)", len(lote))
        return

    for mensagem, ticket in zip(lote, tickets, strict=False):
        if ticket.get("status") == "ok":
            resultado.enviadas += 1
            continue

        detalhe = (ticket.get("details") or {}).get("error")
        if detalhe == ERRO_TOKEN_MORTO:
            resultado.tokens_mortos.append(mensagem.token)
        else:
            logger.warning("Push recusado pelo Expo: %s", ticket.get("message"))
