"""De quem veio a requisicao.

Existia como cinco copias de `_client_ip` — auth, employees, face_templates,
sites e time_entries —, todas lendo `request.client.host`. Isso e verdade
quando a API atende direto e vira mentira assim que ela sobe atras de um proxy
(Railway, Fly.io, qualquer CDN): `request.client.host` passa a ser o endereco
do proxy, e **todo mundo parece vir do mesmo lugar**.

Enquanto isso so alimentava a trilha de auditoria, o preco era um campo errado.
Com o limite de tentativas de login (`login_throttle`), o preco passou a ser
outro: uma regra que bloqueia por IP bloquearia a empresa inteira de uma vez.
"""

from fastapi import Request

from app.core.config import settings

MAX_IP_LENGTH = 45  # comprimento de um IPv6 em texto, que e o que a coluna guarda


def client_ip(request: Request) -> str | None:
    """Endereco de quem chamou, ou `None` quando nao da para atribuir.

    `None` e uma resposta legitima e importante: significa "ha um proxy no
    caminho e nao fomos autorizados a acreditar no que ele diz". Preferir isso a
    devolver o IP do proxy e o que impede uma regra por endereco de tratar
    clientes distintos como um so — e um IP errado na auditoria nao vale mais
    que um campo vazio, porque um dia alguem vai investigar um incidente com
    ele.

    `TRUST_PROXY_HEADERS` so deve ser ligada quando **todo** acesso a API passa
    obrigatoriamente pelo proxy. Se a API tambem for alcancavel direto, o
    cabecalho vira campo livre e qualquer cliente escolhe o proprio endereco.
    """
    encaminhado = request.headers.get("x-forwarded-for")

    if encaminhado:
        if not settings.trust_proxy_headers:
            return None
        # O primeiro da lista e o cliente; os demais sao os proxies que o
        # encaminharam.
        primeiro = encaminhado.split(",")[0].strip()
        return primeiro[:MAX_IP_LENGTH] or None

    return request.client.host[:MAX_IP_LENGTH] if request.client else None
