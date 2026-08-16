"""Endpoints de autenticacao.

Dois publicos separados: `/auth/admin/*` para o painel do RH e
`/auth/employee/*` para o app. Endpoints distintos, e nao um login unico com
flag, porque as credenciais, o formato de entrada e o que cada um pode fazer
sao diferentes.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentPrincipal, Locale, SessionDep, erro_http
from app.core.messages import Msg
from app.core.net import client_ip
from app.models import Employee, User
from app.models.enums import SubjectType
from app.schemas.auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    EmployeeLoginRequest,
    EmployeeLoginResponse,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
)
from app.services import auth as auth_service
from app.services import login_throttle

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais invalidas",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent", "")[:400] or None


def _muitas_tentativas(exc: login_throttle.Throttled, idioma: str) -> HTTPException:
    """429 com `Retry-After`, que e o que um cliente sabe interpretar sozinho."""
    return erro_http(
        status.HTTP_429_TOO_MANY_REQUESTS,
        Msg.MUITAS_TENTATIVAS,
        idioma,
        headers={"Retry-After": str(exc.retry_after)},
        minutes=exc.minutes,
    )


async def _registrar_falha(session: AsyncSession, identidade: str, ip: str | None) -> None:
    """Conta a tentativa e **commita antes** de o endpoint levantar o 401.

    Sem o commit aqui, a dependencia de sessao desfaria a transacao junto com a
    excecao e o contador nunca sairia do zero — o teto existiria no codigo e nao
    no comportamento.
    """
    await login_throttle.record_failure(session, identity=identidade, ip=ip)
    await session.commit()


@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    session: SessionDep,
    idioma: Locale,
) -> AdminLoginResponse:
    """Login do painel administrativo."""
    ip = client_ip(request)
    identidade = login_throttle.identity_key(
        audience="admin", tenant_slug=payload.tenant_slug, identifier=payload.email
    )

    try:
        await login_throttle.ensure_allowed(session, identity=identidade, ip=ip)
    except login_throttle.Throttled as exc:
        raise _muitas_tentativas(exc, idioma) from exc

    try:
        user, tenant = await auth_service.authenticate_admin(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password,
        )
    except auth_service.AuthError as exc:
        await _registrar_falha(session, identidade, ip)
        raise _UNAUTHORIZED from exc

    await login_throttle.clear(session, identity=identidade)

    tokens, _ = await auth_service.issue_token_pair(
        session,
        tenant_id=tenant.id,
        subject_id=user.id,
        subject_type=SubjectType.USER,
        role=user.role.value,
        ip_address=client_ip(request),
        user_agent=_user_agent(request),
    )

    return AdminLoginResponse(tokens=tokens, user=user, tenant=tenant)


@router.post("/employee/login", response_model=EmployeeLoginResponse)
async def employee_login(
    payload: EmployeeLoginRequest,
    request: Request,
    session: SessionDep,
    idioma: Locale,
) -> EmployeeLoginResponse:
    """Login do app do funcionario, com pareamento do aparelho."""
    ip = client_ip(request)
    identidade = login_throttle.identity_key(
        audience="employee",
        tenant_slug=payload.tenant_slug,
        identifier=payload.external_code,
    )

    try:
        await login_throttle.ensure_allowed(session, identity=identidade, ip=ip)
    except login_throttle.Throttled as exc:
        raise _muitas_tentativas(exc, idioma) from exc

    try:
        employee, tenant, device = await auth_service.authenticate_employee(
            session,
            tenant_slug=payload.tenant_slug,
            external_code=payload.external_code,
            password=payload.password,
            device_info=payload.device,
        )
    except auth_service.AuthError as exc:
        await _registrar_falha(session, identidade, ip)
        raise _UNAUTHORIZED from exc

    await login_throttle.clear(session, identity=identidade)

    tokens, _ = await auth_service.issue_token_pair(
        session,
        tenant_id=tenant.id,
        subject_id=employee.id,
        subject_type=SubjectType.EMPLOYEE,
        device_id=device.id,
        ip_address=client_ip(request),
        user_agent=_user_agent(request),
    )

    return EmployeeLoginResponse(
        tokens=tokens,
        employee=employee,
        tenant=tenant,
        device_id=device.id,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: SessionDep,
) -> TokenPair:
    """Troca o refresh token por um par novo.

    Rota unica para os dois publicos: o titular ja esta identificado dentro do
    proprio token guardado.
    """
    try:
        return await auth_service.rotate_refresh_token(
            session,
            raw_token=payload.refresh_token,
            ip_address=client_ip(request),
            user_agent=_user_agent(request),
        )
    except auth_service.AuthError as exc:
        raise _UNAUTHORIZED from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, session: SessionDep) -> Response:
    """Encerra a sessao revogando o refresh token.

    Sempre 204, mesmo com token inexistente: nao ha razao para dizer a quem
    chamou se aquele token era valido.
    """
    await auth_service.revoke_refresh_token(session, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal, session: SessionDep) -> MeResponse:
    """Identidade da sessao atual."""
    if principal.is_admin:
        user = await session.scalar(
            select(User).where(
                User.id == principal.subject_id,
                User.tenant_id == principal.tenant_id,
            )
        )
        if user is None:
            raise _UNAUTHORIZED
        name = user.name
    else:
        employee = await session.scalar(
            select(Employee).where(
                Employee.id == principal.subject_id,
                Employee.tenant_id == principal.tenant_id,
            )
        )
        if employee is None:
            raise _UNAUTHORIZED
        name = employee.name

    return MeResponse(
        subject_id=principal.subject_id,
        subject_type=principal.subject_type.value,
        tenant_id=principal.tenant_id,
        role=principal.role,
        device_id=principal.device_id,
        name=name,
    )
