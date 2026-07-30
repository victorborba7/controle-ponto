"""Endpoints de autenticacao.

Dois publicos separados: `/auth/admin/*` para o painel do RH e
`/auth/employee/*` para o app. Endpoints distintos, e nao um login unico com
flag, porque as credenciais, o formato de entrada e o que cada um pode fazer
sao diferentes.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, SessionDep
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

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais invalidas",
    headers={"WWW-Authenticate": "Bearer"},
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent", "")[:400] or None


@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    session: SessionDep,
) -> AdminLoginResponse:
    """Login do painel administrativo."""
    try:
        user, tenant = await auth_service.authenticate_admin(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password,
        )
    except auth_service.AuthError as exc:
        raise _UNAUTHORIZED from exc

    tokens, _ = await auth_service.issue_token_pair(
        session,
        tenant_id=tenant.id,
        subject_id=user.id,
        subject_type=SubjectType.USER,
        role=user.role.value,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )

    return AdminLoginResponse(tokens=tokens, user=user, tenant=tenant)


@router.post("/employee/login", response_model=EmployeeLoginResponse)
async def employee_login(
    payload: EmployeeLoginRequest,
    request: Request,
    session: SessionDep,
) -> EmployeeLoginResponse:
    """Login do app do funcionario, com pareamento do aparelho."""
    try:
        employee, tenant, device = await auth_service.authenticate_employee(
            session,
            tenant_slug=payload.tenant_slug,
            external_code=payload.external_code,
            password=payload.password,
            device_info=payload.device,
        )
    except auth_service.AuthError as exc:
        raise _UNAUTHORIZED from exc

    tokens, _ = await auth_service.issue_token_pair(
        session,
        tenant_id=tenant.id,
        subject_id=employee.id,
        subject_type=SubjectType.EMPLOYEE,
        device_id=device.id,
        ip_address=_client_ip(request),
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
            ip_address=_client_ip(request),
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
