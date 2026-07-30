"""Consulta de funcionarios.

Nesta etapa existe apenas leitura, com dois propositos: dar ao painel algo
util desde ja e servir de superficie concreta para o teste de isolamento entre
tenants. O CRUD completo entra na Etapa 4.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentAdmin, TenantRepo
from app.models import Employee
from app.schemas.employee import EmployeeList, EmployeeSummary

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeeList)
async def list_employees(
    _: CurrentAdmin,
    repo: TenantRepo,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EmployeeList:
    """Lista os funcionarios da empresa do token.

    O repositorio ja aplica o filtro de tenant — nao ha parametro de empresa
    a ser informado, nem como informa-lo.
    """
    employees = await repo.list(Employee, limit=limit, offset=offset)
    total = await repo.count(Employee)
    return EmployeeList(
        items=[EmployeeSummary.model_validate(e) for e in employees],
        total=total,
    )


@router.get("/{employee_id}", response_model=EmployeeSummary)
async def get_employee(
    employee_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
) -> EmployeeSummary:
    """Busca um funcionario pelo id.

    Id de outra empresa responde 404, e nao 403: confirmar que o registro
    existe em algum lugar ja seria vazamento.
    """
    employee = await repo.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funcionario nao encontrado",
        )
    return EmployeeSummary.model_validate(employee)
