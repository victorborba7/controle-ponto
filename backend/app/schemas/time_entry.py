"""Schemas do registro de ponto."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EntryType, LocationMethod, TimeEntryStatus


class TimeEntrySummary(BaseModel):
    """Um ponto como o painel e o app o veem.

    Traz a evidencia resumida — score do rosto, metodo de localizacao,
    confianca — porque um registro de ponto sem o "como foi comprovado" nao
    pode ser contestado nem defendido.

    Sem `selfie_image_key`: a chave da imagem e interna e nao trafega.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    entry_type: EntryType
    recorded_at: datetime
    client_recorded_at: datetime | None = None

    status: TimeEntryStatus
    decision_reason: str | None = None

    face_match_score: float | None = None
    liveness_passed: bool | None = None

    location_method: LocationMethod
    location_confidence: float | None = None
    site_id: uuid.UUID | None = None
    beacon_id: uuid.UUID | None = None
    wifi_network_id: uuid.UUID | None = None
    beacon_rssi: int | None = None
    distance_to_site_m: float | None = None

    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime


class TimeEntryWithEmployee(TimeEntrySummary):
    """Para a listagem do RH, que precisa saber de quem e cada linha."""

    employee_name: str
    employee_code: str
    site_name: str | None = None


class TimeEntryList(BaseModel):
    items: list[TimeEntryWithEmployee]
    total: int


class MyTimeEntryList(BaseModel):
    items: list[TimeEntrySummary]
    total: int


class TimeEntryReview(BaseModel):
    """Decisao do RH sobre um ponto pendente."""

    approved: bool
    note: str | None = Field(default=None, max_length=1000)


class TimeEntryCreated(BaseModel):
    """Resposta ao app depois de bater o ponto.

    `message` existe para o app exibir sem precisar traduzir status: o
    funcionario quer saber se o ponto valeu, nao qual enum foi gravado.
    """

    entry: TimeEntrySummary
    message: str
    duplicate: bool = False
