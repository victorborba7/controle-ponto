"""Regras de cadastro de funcionarios."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.repository import TenantRepository
from app.models import Employee, FaceTemplate, Site
from app.models.enums import EmployeeStatus
from app.schemas.employee import EmployeeCreate, EmployeeUpdate


class EmployeeError(Exception):
    """Falha de regra de negocio no cadastro."""


class DuplicateEmployeeError(EmployeeError):
    pass


class InvalidSiteError(EmployeeError):
    pass


async def create_employee(repo: TenantRepository, payload: EmployeeCreate) -> Employee:
    """Cadastra um funcionario.

    Checa duplicidade antes de inserir para devolver um erro compreensivel em
    vez do estouro de constraint do banco, que nao diz ao RH qual campo
    colidiu.
    """
    await _ensure_unique(repo, external_code=payload.external_code, cpf=payload.cpf)
    await _ensure_site_belongs_to_tenant(repo, payload.default_site_id)

    employee = Employee(
        external_code=payload.external_code,
        name=payload.name,
        cpf=payload.cpf,
        email=payload.email,
        phone=payload.phone,
        job_title=payload.job_title,
        hired_at=payload.hired_at,
        default_site_id=payload.default_site_id,
        status=EmployeeStatus.ACTIVE,
    )

    if payload.initial_password:
        employee.password_hash = hash_password(payload.initial_password)
        # Senha definida pelo RH e provisoria: o funcionario troca no primeiro
        # acesso, para o RH nao ficar sabendo a senha de ninguem.
        employee.must_change_password = True

    repo.add(employee)
    await repo.flush()
    return employee


async def update_employee(
    repo: TenantRepository,
    employee: Employee,
    payload: EmployeeUpdate,
) -> Employee:
    """Aplica uma atualizacao parcial."""
    changes = payload.model_dump(exclude_unset=True)

    if "cpf" in changes and changes["cpf"] is not None:
        await _ensure_unique(repo, cpf=changes["cpf"], ignore_id=employee.id)

    if "default_site_id" in changes:
        await _ensure_site_belongs_to_tenant(repo, changes["default_site_id"])

    for field, value in changes.items():
        setattr(employee, field, value)

    await repo.flush()
    return employee


async def set_password(employee: Employee, new_password: str) -> None:
    """Define a senha do app e forca a troca no proximo acesso."""
    employee.password_hash = hash_password(new_password)
    employee.must_change_password = True


async def count_active_templates(session: AsyncSession, employee: Employee) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(FaceTemplate)
            .where(
                FaceTemplate.tenant_id == employee.tenant_id,
                FaceTemplate.employee_id == employee.id,
                FaceTemplate.is_active.is_(True),
            )
        )
    ) or 0


async def _ensure_unique(
    repo: TenantRepository,
    *,
    external_code: str | None = None,
    cpf: str | None = None,
    ignore_id: uuid.UUID | None = None,
) -> None:
    """Matricula e CPF sao unicos dentro da empresa, nao globalmente."""
    if external_code is not None:
        query = repo.query(Employee).where(Employee.external_code == external_code)
        if ignore_id is not None:
            query = query.where(Employee.id != ignore_id)
        if await repo.session.scalar(query.limit(1)) is not None:
            raise DuplicateEmployeeError(f"Ja existe funcionario com a matricula {external_code}")

    if cpf is not None:
        query = repo.query(Employee).where(Employee.cpf == cpf)
        if ignore_id is not None:
            query = query.where(Employee.id != ignore_id)
        if await repo.session.scalar(query.limit(1)) is not None:
            raise DuplicateEmployeeError("Ja existe funcionario com este CPF")


async def _ensure_site_belongs_to_tenant(
    repo: TenantRepository, site_id: uuid.UUID | None
) -> None:
    """Impede apontar o funcionario para um local de outra empresa.

    Sem esta checagem, um id de site valido em outro tenant seria aceito — a FK
    do banco nao sabe nada sobre tenants.
    """
    if site_id is None:
        return
    if await repo.get(Site, site_id) is None:
        raise InvalidSiteError("Local nao encontrado nesta empresa")
