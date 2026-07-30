"""Dependencias compartilhadas pelos endpoints.

A cadeia e sempre a mesma: Bearer token -> JWT validado -> Principal ->
TenantRepository. Um endpoint que peca `TenantRepo` ja recebe acesso a dados
restrito ao tenant do token, sem ter de fazer nada.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.core.tenancy import Principal, principal_from_claims
from app.db.repository import TenantRepository
from app.db.session import get_session
from app.models.enums import UserRole

# auto_error=False para responder 401 com o mesmo formato dos demais erros,
# em vez do 403 que o HTTPBearer devolve por padrao quando falta o cabecalho.
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais invalidas ou expiradas",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Extrai a identidade do Bearer token.

    Toda falha — cabecalho ausente, assinatura invalida, token expirado,
    claims malformadas — vira o mesmo 401. Nao informar *qual* checagem falhou
    e deliberado: a diferenca so ajudaria quem estivesse sondando a API.
    """
    if credentials is None or not credentials.credentials:
        raise _INVALID_CREDENTIALS

    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise _INVALID_CREDENTIALS

    principal = principal_from_claims(claims)
    if principal is None:
        raise _INVALID_CREDENTIALS

    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_admin_principal(principal: CurrentPrincipal) -> Principal:
    """Exige um usuario do painel. Token de funcionario nao serve."""
    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este recurso e restrito ao painel administrativo",
        )
    return principal


async def get_employee_principal(principal: CurrentPrincipal) -> Principal:
    """Exige um funcionario. Token de admin nao serve.

    Bloquear o admin aqui nao e excesso: bater ponto e ato pessoal, e um
    administrador com token valido nao pode registrar presenca por ninguem.
    """
    if not principal.is_employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este recurso e restrito ao app do funcionario",
        )
    return principal


CurrentAdmin = Annotated[Principal, Depends(get_admin_principal)]
CurrentEmployee = Annotated[Principal, Depends(get_employee_principal)]


def require_roles(*roles: UserRole):
    """Fabrica de dependencia que restringe por papel.

        @router.delete("/employees/{id}", dependencies=[Depends(require_roles(UserRole.OWNER))])
    """

    async def _check(principal: CurrentAdmin) -> Principal:
        if not principal.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente para esta operacao",
            )
        return principal

    return _check


async def get_tenant_repository(
    principal: CurrentPrincipal,
    session: SessionDep,
) -> TenantRepository:
    """Repositorio ja restrito ao tenant do token."""
    return TenantRepository(session, principal.tenant_id)


TenantRepo = Annotated[TenantRepository, Depends(get_tenant_repository)]
