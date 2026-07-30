"""Schemas de funcionario.

Somente leitura nesta etapa — o CRUD completo entra na Etapa 4.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.enums import EmployeeStatus


class EmployeeSummary(BaseModel):
    """Funcionario como o painel lista.

    Sem CPF e sem qualquer dado biometrico: listagem nao precisa deles, e dado
    pessoal que nao trafega e dado que nao vaza.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_code: str
    name: str
    job_title: str | None = None
    status: EmployeeStatus
    hired_at: date | None = None


class EmployeeList(BaseModel):
    items: list[EmployeeSummary]
    total: int
