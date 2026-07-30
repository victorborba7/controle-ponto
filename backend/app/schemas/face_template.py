"""Schemas do cadastro biometrico.

**Nenhum destes modelos tem campo de embedding, e isso e proposital.** O vetor
facial e dado pessoal sensivel pela LGPD e nao tem uso legitimo fora do
servidor: o painel exibe qualidade e data, o app nunca ve nada disto. Um teste
verifica que a palavra "embedding" nao aparece em resposta alguma.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConsentDeclaration(BaseModel):
    """Declaracao de que o consentimento do funcionario foi colhido.

    Obrigatoria no cadastro biometrico: sem base legal nao ha tratamento de
    dado sensivel, entao a API recusa o enrollment se ela nao vier.
    """

    policy_version: str = Field(min_length=1, max_length=20)
    granted: bool


class FaceTemplateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quality_score: float | None
    model_name: str
    model_version: str
    is_active: bool
    created_at: datetime


class RejectedImage(BaseModel):
    """Foto que nao virou template, e por que.

    O motivo volta em codigo (`blurry`, `face_too_small`) para o painel poder
    traduzir numa orientacao acionavel — "firme a mao", "chegue mais perto" —
    em vez de exibir um erro tecnico.
    """

    filename: str
    reason: str
    issues: list[str] = []


class EnrollmentResult(BaseModel):
    employee_id: uuid.UUID
    created: list[FaceTemplateSummary]
    rejected: list[RejectedImage]
    deactivated_previous: int
    consent_id: uuid.UUID


class FaceTemplateList(BaseModel):
    items: list[FaceTemplateSummary]
    total: int
