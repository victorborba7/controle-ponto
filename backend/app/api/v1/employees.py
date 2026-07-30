"""Cadastro e consulta de funcionarios.

Restrito ao painel administrativo. Todo acesso a dados passa pelo
`TenantRepo`, entao nao existe caminho em que um id de outra empresa seja
alcancado — mesmo que venha na URL.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentAdmin, SessionDep, TenantRepo, require_roles
from app.models import Employee
from app.models.enums import AuditAction, EmployeeStatus, UserRole
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDetail,
    EmployeeList,
    EmployeeSummary,
    EmployeeUpdate,
    PasswordReset,
)
from app.services import audit
from app.services import employee as employee_service

router = APIRouter(prefix="/employees", tags=["employees"])

# Consultar e papel de qualquer perfil do painel; alterar cadastro nao e de
# quem so tem acesso de leitura.
ESCRITA = [Depends(require_roles(UserRole.OWNER, UserRole.HR))]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _get_or_404(repo: TenantRepo, employee_id: uuid.UUID) -> Employee:
    employee = await repo.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funcionario nao encontrado",
        )
    return employee


@router.get("", response_model=EmployeeList)
async def list_employees(
    _: CurrentAdmin,
    repo: TenantRepo,
    status_filter: EmployeeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EmployeeList:
    query = repo.query(Employee).order_by(Employee.name)
    if status_filter is not None:
        query = query.where(Employee.status == status_filter)

    result = await repo.session.execute(query.limit(limit).offset(offset))
    employees = list(result.scalars().all())

    return EmployeeList(
        items=[EmployeeSummary.model_validate(item) for item in employees],
        total=await repo.count(Employee),
    )


@router.post(
    "",
    response_model=EmployeeDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITA,
)
async def create_employee(
    payload: EmployeeCreate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> EmployeeDetail:
    try:
        employee = await employee_service.create_employee(repo, payload)
    except employee_service.DuplicateEmployeeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except employee_service.InvalidSiteError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type="employee",
        entity_id=employee.id,
        payload={"external_code": employee.external_code},
        description=f"Funcionario {employee.name} cadastrado",
        ip_address=_client_ip(request),
    )

    return await _to_detail(session, employee)


@router.get("/{employee_id}", response_model=EmployeeDetail)
async def get_employee(
    employee_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
) -> EmployeeDetail:
    """Id de outra empresa responde 404, e nao 403.

    Um 403 confirmaria que o registro existe em algum lugar, o que ja e
    vazamento.
    """
    employee = await _get_or_404(repo, employee_id)
    return await _to_detail(session, employee)


@router.patch("/{employee_id}", response_model=EmployeeDetail, dependencies=ESCRITA)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> EmployeeDetail:
    employee = await _get_or_404(repo, employee_id)

    try:
        await employee_service.update_employee(repo, employee, payload)
    except employee_service.DuplicateEmployeeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except employee_service.InvalidSiteError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=employee.id,
        payload={"campos": sorted(payload.model_dump(exclude_unset=True).keys())},
        ip_address=_client_ip(request),
    )

    return await _to_detail(session, employee)


@router.post(
    "/{employee_id}/deactivate", response_model=EmployeeDetail, dependencies=ESCRITA
)
async def deactivate_employee(
    employee_id: uuid.UUID,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> EmployeeDetail:
    """Desliga o funcionario sem apagar nada.

    Delete real levaria junto o historico de pontos, que precisa sobreviver ao
    desligamento por obrigacao trabalhista.
    """
    employee = await _get_or_404(repo, employee_id)
    employee.status = EmployeeStatus.INACTIVE
    await repo.flush()

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=employee.id,
        description=f"Funcionario {employee.name} desativado",
        ip_address=_client_ip(request),
    )

    return await _to_detail(session, employee)


@router.post(
    "/{employee_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ESCRITA,
)
async def reset_password(
    employee_id: uuid.UUID,
    payload: PasswordReset,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> None:
    """Define a senha do app. O funcionario e obrigado a troca-la no acesso."""
    employee = await _get_or_404(repo, employee_id)
    await employee_service.set_password(employee, payload.new_password)
    await repo.flush()

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=employee.id,
        description="Senha do app redefinida pelo RH",
        ip_address=_client_ip(request),
    )


async def _to_detail(session: SessionDep, employee: Employee) -> EmployeeDetail:
    detail = EmployeeDetail.model_validate(employee)
    detail.has_app_credentials = employee.password_hash is not None
    detail.active_face_templates = await employee_service.count_active_templates(
        session, employee
    )
    return detail
