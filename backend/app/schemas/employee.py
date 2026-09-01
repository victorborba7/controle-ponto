"""Schemas de funcionario."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.core.security import SENHA_MINIMA
from app.models.enums import DevicePlatform, EmployeeStatus


def normalizar_cpf(value: str) -> str:
    """Aceita com ou sem pontuacao, mas exige 11 digitos.

    Normaliza na entrada porque o mesmo CPF chega escrito de varias formas, e
    duas grafias do mesmo numero furariam a restricao de unicidade por tenant.
    Devolve formatado, para o RH reconhecer na tela.
    """
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 11:
        raise ValueError("CPF deve ter 11 digitos")
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


CPF = Annotated[str, AfterValidator(normalizar_cpf)]


class EmployeeCreate(BaseModel):
    external_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=200)
    cpf: CPF | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    job_title: str | None = Field(default=None, max_length=120)
    hired_at: date | None = None
    default_site_id: uuid.UUID | None = None
    # Senha inicial do app. Sem ela o funcionario fica cadastrado mas ainda nao
    # consegue entrar — util para o RH cadastrar antes da admissao.
    initial_password: str | None = Field(
        default=None, min_length=SENHA_MINIMA, max_length=200
    )


class EmployeeUpdate(BaseModel):
    """Atualizacao parcial: campo ausente permanece como esta.

    `external_code` fica de fora de proposito — e a matricula usada no login e
    referenciada em relatorio; trocar exigiria uma operacao propria e explicita.
    """

    name: str | None = Field(default=None, min_length=2, max_length=200)
    cpf: CPF | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    job_title: str | None = Field(default=None, max_length=120)
    hired_at: date | None = None
    default_site_id: uuid.UUID | None = None
    status: EmployeeStatus | None = None


class EmployeeSummary(BaseModel):
    """Funcionario como o painel lista.

    Sem CPF: listagem nao precisa dele, e dado pessoal que nao trafega e dado
    que nao vaza.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_code: str
    name: str
    job_title: str | None = None
    status: EmployeeStatus
    hired_at: date | None = None


class EmployeeDetail(EmployeeSummary):
    """Ficha completa, na tela de um funcionario especifico.

    Traz CPF e contato — mas nunca hash de senha nem embedding facial.
    """

    cpf: str | None = None
    email: str | None = None
    phone: str | None = None
    default_site_id: uuid.UUID | None = None
    terminated_at: date | None = None
    has_app_credentials: bool = False
    active_face_templates: int = 0
    created_at: datetime


class EmployeeList(BaseModel):
    items: list[EmployeeSummary]
    total: int


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=SENHA_MINIMA, max_length=200)


# --------------------------------------------------------------------------
# Aparelhos pareados
# --------------------------------------------------------------------------


class DeviceSummary(BaseModel):
    """Aparelho pareado, como o painel o mostra.

    Sem o `device_fingerprint`: e o segredo que amarra o celular a pessoa, e
    quem o tivesse poderia se passar pelo aparelho no proximo login. A tela
    identifica pelo modelo e pela data — que e o que um humano reconhece.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: DevicePlatform
    model: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class DeviceList(BaseModel):
    items: list[DeviceSummary]
    total: int
