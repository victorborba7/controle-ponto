"""Dependencias compartilhadas pelos endpoints.

A cadeia e sempre a mesma: Bearer token -> JWT validado -> Principal ->
TenantRepository. Um endpoint que peca `TenantRepo` ja recebe acesso a dados
restrito ao tenant do token, sem ter de fazer nada.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.messages import Msg, negociar_idioma, traduzir
from app.core.security import decode_access_token
from app.core.tenancy import Principal, principal_from_claims
from app.db.repository import TenantRepository
from app.db.session import get_session
from app.facial import get_face_engine
from app.facial.runner import AsyncFaceEngine
from app.models.enums import UserRole
from app.services.storage import Storage, build_storage

# auto_error=False para responder 401 com o mesmo formato dos demais erros,
# em vez do 403 que o HTTPBearer devolve por padrao quando falta o cabecalho.
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_locale(
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None,
) -> str:
    """Idioma da resposta, negociado pelo cabecalho do cliente.

    Fica aqui, e nao num middleware, porque so quem monta a resposta precisa
    dele — servico nenhum recebe idioma como argumento.
    """
    return negociar_idioma(accept_language)


Locale = Annotated[str, Depends(get_locale)]


def erro_http(
    status_code: int,
    chave: Msg,
    idioma: str,
    /,
    headers: dict[str, str] | None = None,
    **parametros: object,
) -> HTTPException:
    """Monta o `HTTPException` com o texto ja no idioma de quem pediu.

    `detail` continua sendo string, e nao um objeto com `code`: a negociacao
    por `Accept-Language` ja entrega o texto pronto, entao o codigo so serviria
    para o cliente ramificar comportamento — o que nenhum dos dois faz hoje.
    Acrescentar depois e aditivo; mudar o formato agora quebraria os dois
    clientes de uma vez.
    """
    return HTTPException(
        status_code=status_code,
        detail=traduzir(chave, idioma, **parametros),
        headers=headers,
    )


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    idioma: Locale,
) -> Principal:
    """Extrai a identidade do Bearer token.

    Toda falha — cabecalho ausente, assinatura invalida, token expirado,
    claims malformadas — vira o mesmo 401. Nao informar *qual* checagem falhou
    e deliberado: a diferenca so ajudaria quem estivesse sondando a API.
    """
    invalidas = erro_http(
        status.HTTP_401_UNAUTHORIZED,
        Msg.SESSAO_EXPIRADA,
        idioma,
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise invalidas

    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise invalidas

    principal = principal_from_claims(claims)
    if principal is None:
        raise invalidas

    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_admin_principal(principal: CurrentPrincipal, idioma: Locale) -> Principal:
    """Exige um usuario do painel. Token de funcionario nao serve."""
    if not principal.is_admin:
        raise erro_http(status.HTTP_403_FORBIDDEN, Msg.SO_PAINEL, idioma)
    return principal


async def get_employee_principal(principal: CurrentPrincipal, idioma: Locale) -> Principal:
    """Exige um funcionario. Token de admin nao serve.

    Bloquear o admin aqui nao e excesso: bater ponto e ato pessoal, e um
    administrador com token valido nao pode registrar presenca por ninguem.
    """
    if not principal.is_employee:
        raise erro_http(status.HTTP_403_FORBIDDEN, Msg.SO_APP, idioma)
    return principal


CurrentAdmin = Annotated[Principal, Depends(get_admin_principal)]
CurrentEmployee = Annotated[Principal, Depends(get_employee_principal)]


def require_roles(*roles: UserRole):
    """Fabrica de dependencia que restringe por papel.

    @router.delete("/employees/{id}", dependencies=[Depends(require_roles(UserRole.OWNER))])
    """

    async def _check(principal: CurrentAdmin, idioma: Locale) -> Principal:
        if not principal.has_role(*roles):
            raise erro_http(status.HTTP_403_FORBIDDEN, Msg.SEM_PERMISSAO, idioma)
        return principal

    return _check


async def get_tenant_repository(
    principal: CurrentPrincipal,
    session: SessionDep,
) -> TenantRepository:
    """Repositorio ja restrito ao tenant do token."""
    return TenantRepository(session, principal.tenant_id)


TenantRepo = Annotated[TenantRepository, Depends(get_tenant_repository)]


@lru_cache(maxsize=1)
def _storage() -> Storage:
    """Instancia unica: nao ha estado por requisicao a isolar."""
    return build_storage(settings.storage_path, settings.storage_encryption_key)


def get_storage() -> Storage:
    return _storage()


def get_engine() -> AsyncFaceEngine:
    """Engine facial da aplicacao.

    Exposta como dependencia (e nao importada direto nos endpoints) para o
    teste conseguir substitui-la por uma engine controlada.
    """
    return get_face_engine()


StorageDep = Annotated[Storage, Depends(get_storage)]
FaceEngineDep = Annotated[AsyncFaceEngine, Depends(get_engine)]
