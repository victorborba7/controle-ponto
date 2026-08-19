"""Schemas de entrada e saida da autenticacao."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import DevicePlatform, UserRole


class AdminLoginRequest(BaseModel):
    # O slug do tenant e obrigatorio porque email e unico *por empresa*, nao
    # globalmente — a mesma pessoa pode administrar mais de um cliente.
    tenant_slug: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class DeviceInfo(BaseModel):
    """Identificacao do aparelho, enviada pelo app a cada login."""

    fingerprint: str = Field(min_length=8, max_length=255)
    platform: DevicePlatform
    model: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=50)
    app_version: str | None = Field(default=None, max_length=30)


class EmployeeLoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=60)
    # Matricula, nao email: nem todo operario de hangar tem email corporativo.
    external_code: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    device: DeviceInfo


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=200)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos de validade do access token


class AdminProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    external_code: str
    job_title: str | None = None
    must_change_password: bool
    # Vem do login para o app decidir a tela inicial sem uma segunda chamada —
    # e para funcionar depois, offline, a partir do perfil guardado.
    face_enrolled: bool = True


class TenantInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class AdminLoginResponse(BaseModel):
    tokens: TokenPair
    user: AdminProfile
    tenant: TenantInfo


class EmployeeLoginResponse(BaseModel):
    tokens: TokenPair
    employee: EmployeeProfile
    tenant: TenantInfo
    device_id: uuid.UUID


class MeResponse(BaseModel):
    """Identidade da sessao atual, para o cliente saber o que pode exibir."""

    subject_id: uuid.UUID
    subject_type: str
    tenant_id: uuid.UUID
    role: UserRole | None = None
    device_id: uuid.UUID | None = None
    name: str
    # Só faz sentido para funcionário; None no painel. O app decide com isto se
    # abre a tela de ponto ou a de cadastro do rosto — perguntar tentando bater
    # ponto e receber erro seria dizer ao recém-contratado que ele fez algo
    # errado, quando só falta um passo que ninguém explicou.
    face_enrolled: bool | None = None
