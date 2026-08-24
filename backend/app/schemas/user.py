"""Usuarios do painel — quem administra, nao quem bate ponto."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole

#: Minimo da senha inicial. Igual ao do script de troca por linha de comando:
#: duas regras diferentes para a mesma senha so ensinariam a contornar a maior.
SENHA_MINIMA = 12


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=200)
    role: UserRole = UserRole.HR
    password: str = Field(min_length=SENHA_MINIMA, max_length=200)


class UserUpdate(BaseModel):
    """Campos opcionais: o que nao vier fica como esta.

    O email fica de fora de proposito. Ele identifica o login e aparece na
    trilha de auditoria; trocar por baixo transformaria o historico de uma
    pessoa no historico de outra. Quem precisa mudar de email cria um usuario
    novo e desativa o antigo.
    """

    name: str | None = Field(default=None, min_length=2, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=SENHA_MINIMA, max_length=200)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserList(BaseModel):
    items: list[UserSummary]
