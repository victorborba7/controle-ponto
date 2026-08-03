"""Registro de ponto: orquestracao do fluxo completo.

Junta tudo que as etapas anteriores construiram:

    aparelho pareado -> qualidade da foto -> rosto 1:1 contra os templates
    -> cadeia de localizacao -> decisao -> gravacao

A decisao em si vive em `time_entry_decision`, e a cadeia de localizacao em
`location_validator`. Aqui fica a costura: o que consultar, em que ordem, e o
que gravar.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.messages import IDIOMA_PADRAO, Msg, traduzir
from app.db.repository import TenantRepository
from app.facial import FacialError, MatchCandidate, MatchOutcome
from app.facial.imaging import inspect_image
from app.facial.runner import AsyncFaceEngine
from app.models import Device, Employee, FaceTemplate, TimeEntry
from app.models.enums import EntryType, LocationMethod, TimeEntryStatus
from app.schemas.evidence import LocationEvidence
from app.services import enrollment as enrollment_service
from app.services import punch_config as punch_config_service
from app.services.location import load_registry
from app.services.location_validator import (
    build_audit_payload,
    validate_location,
)
from app.services.storage import Storage
from app.services.time_entry_decision import EntryDecision, decide

SELFIE_STORAGE_PREFIX = "selfies"


class TimeEntryError(Exception):
    """Falha que impede o registro do ponto.

    Carrega a chave da mensagem, nao o texto: o servico roda sem saber o
    idioma do aparelho que enviou a batida. A borda HTTP resolve. Ver
    `app.core.messages`.
    """

    chave: Msg = Msg.IMAGEM_ILEGIVEL

    def __init__(self, chave: Msg | None = None, /, **parametros: object) -> None:
        if chave is not None:
            self.chave = chave
        self.parametros = parametros
        super().__init__(traduzir(self.chave, IDIOMA_PADRAO, **parametros))


class DeviceNotTrustedError(TimeEntryError):
    chave = Msg.FACA_LOGIN_DE_NOVO


class NoFaceTemplatesError(TimeEntryError):
    chave = Msg.ROSTO_NAO_CADASTRADO


class FaceRejectedError(TimeEntryError):
    """Rosto claramente diferente do cadastro."""

    chave = Msg.ROSTO_NAO_RECONHECIDO

    def __init__(self, *, score: float | None, **parametros: object) -> None:
        super().__init__(**parametros)
        self.score = score


class StaleTemplateError(TimeEntryError):
    """Ha template, mas de um modelo que nao esta mais em uso."""

    chave = Msg.CADASTRO_FACIAL_DESATUALIZADO


class DeviceUnlinkedError(TimeEntryError):
    chave = Msg.APARELHO_DESVINCULADO


class TooSoonError(TimeEntryError):
    chave = Msg.BATIDA_REPETIDA

    def __init__(self, *, existing: TimeEntry, **parametros: object) -> None:
        super().__init__(**parametros)
        self.existing = existing


@dataclass
class PunchResult:
    entry: TimeEntry
    decision: EntryDecision
    duplicate: bool = False


async def punch(
    session: AsyncSession,
    repo: TenantRepository,
    engine: AsyncFaceEngine,
    storage: Storage,
    *,
    employee: Employee,
    device: Device | None,
    selfie: bytes,
    evidence: LocationEvidence,
    entry_type: EntryType | None = None,
    label: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    client_recorded_at: datetime | None = None,
) -> PunchResult:
    """Registra o ponto do funcionario."""
    now = datetime.now(UTC)

    # --- Reenvio da mesma batida ---
    # Antes de qualquer processamento: o motivo de existir e justamente a area
    # sem sinal do hangar, onde o app reenvia sem saber se a primeira chegou.
    if idempotency_key:
        anterior = await _find_by_idempotency_key(repo, idempotency_key)
        if anterior is not None:
            return PunchResult(
                entry=anterior,
                decision=EntryDecision(
                    status=anterior.status,
                    reason=anterior.decision_reason or "",
                    chave=Msg.PONTO_JA_REGISTRADO,
                ),
                duplicate=True,
            )

    _ensure_device_trusted(employee, device)

    # Antes do rosto e da localizacao: campo obrigatorio faltando e recusa
    # barata, e recusar depois do processamento gastaria a inferencia facial
    # para dizer "escreva uma observacao".
    config = await punch_config_service.load(session, repo)
    declarado = punch_config_service.resolve(config, label=label, note=note)

    ultimo = await _last_entry(repo, employee)
    _ensure_not_too_soon(ultimo, now)

    # Precedencia: o que o chamador impos, depois o tipo que o rotulo escolhido
    # carrega, e so entao a alternancia automatica.
    tipo = entry_type or declarado.entry_type or _deduce_entry_type(ultimo)

    # --- Rosto ---
    templates = await enrollment_service.load_active_templates(session, employee)
    if not templates:
        raise NoFaceTemplatesError()

    face_score, face_outcome, template_id = await _match_face(engine, selfie, templates)

    if face_outcome is MatchOutcome.NO_MATCH:
        # Nem o ponto, nem a selfie sao gravados. A foto e de alguem que o
        # sistema acabou de concluir NAO ser o titular — guardar biometria de
        # um terceiro que nunca consentiu seria criar o problema que a LGPD
        # existe para evitar. A tentativa fica na trilha de auditoria, que e
        # onde a investigacao de seguranca precisa dela.
        raise FaceRejectedError(score=face_score)

    # --- Localizacao ---
    registry = await load_registry(repo)
    veredito = validate_location(evidence, registry)

    # --- Decisao ---
    skew = (now - client_recorded_at).total_seconds() if client_recorded_at else 0.0
    decision = decide(
        face_outcome=face_outcome,
        face_score=face_score,
        location=veredito,
        clock_skew_seconds=skew,
        max_clock_skew_seconds=settings.time_entry_max_clock_skew_seconds,
    )

    selfie_key = await storage.save(
        selfie,
        prefix=SELFIE_STORAGE_PREFIX,
        image_format=inspect_image(selfie).format,
    )

    entry = TimeEntry(
        employee_id=employee.id,
        device_id=device.id if device else None,
        entry_type=tipo,
        label=declarado.label,
        note=declarado.note,
        # Horario do servidor: e o que vale juridicamente. O do aparelho fica
        # gravado ao lado, e a divergencia entre os dois ja entrou na decisao.
        recorded_at=now,
        client_recorded_at=client_recorded_at,
        face_match_score=face_score,
        matched_face_template_id=template_id,
        selfie_image_key=selfie_key,
        location_method=veredito.method,
        location_confidence=veredito.confidence,
        site_id=veredito.site_id,
        beacon_id=veredito.beacon_id,
        wifi_network_id=veredito.wifi_network_id,
        beacon_rssi=veredito.beacon_rssi,
        latitude=evidence.gps.latitude if evidence.gps else None,
        longitude=evidence.gps.longitude if evidence.gps else None,
        gps_accuracy_m=evidence.gps.accuracy_m if evidence.gps else None,
        distance_to_site_m=veredito.distance_to_site_m,
        location_raw=build_audit_payload(evidence, veredito),
        status=decision.status,
        decision_reason=decision.reason,
        idempotency_key=idempotency_key,
    )
    repo.add(entry)
    await repo.flush()

    return PunchResult(entry=entry, decision=decision)


# --------------------------------------------------------------------------
# Regras de negocio
# --------------------------------------------------------------------------


def _ensure_device_trusted(employee: Employee, device: Device | None) -> None:
    """O ponto tem de vir do aparelho pareado ao funcionario.

    Sem isso, uma credencial vazada bateria ponto de qualquer celular. O
    pareamento nao impede fraude sozinho, mas obriga quem tentar a passar
    tambem pelo reconhecimento facial no aparelho certo.
    """
    if device is None:
        raise DeviceNotTrustedError()
    if device.revoked_at is not None:
        raise DeviceUnlinkedError()
    if device.employee_id != employee.id:
        raise DeviceNotTrustedError()


def _ensure_not_too_soon(ultimo: TimeEntry | None, now: datetime) -> None:
    """Duas batidas coladas sao o mesmo toque repetido, nao dois eventos."""
    if ultimo is None:
        return

    intervalo = (now - ultimo.recorded_at).total_seconds()
    if intervalo < settings.time_entry_min_interval_seconds:
        raise TooSoonError(existing=ultimo)


def _deduce_entry_type(ultimo: TimeEntry | None) -> EntryType:
    """Alterna entrada e saida a partir da ultima batida.

    Deduzir em vez de perguntar tira do funcionario uma escolha que ele pode
    errar — e um erro ai vira hora extra fantasma ou falta indevida.

    Um registro recusado nao entra na conta porque nunca e gravado, e um
    pendente entra: ele representa uma batida que aconteceu e provavelmente
    sera aprovada.
    """
    if ultimo is None:
        return EntryType.IN
    return EntryType.OUT if ultimo.entry_type is EntryType.IN else EntryType.IN


async def _last_entry(repo: TenantRepository, employee: Employee) -> TimeEntry | None:
    result = await repo.session.execute(
        repo.query(TimeEntry)
        .where(TimeEntry.employee_id == employee.id)
        .order_by(desc(TimeEntry.recorded_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_by_idempotency_key(repo: TenantRepository, key: str) -> TimeEntry | None:
    return await repo.session.scalar(
        repo.query(TimeEntry).where(TimeEntry.idempotency_key == key).limit(1)
    )


async def _match_face(engine: AsyncFaceEngine, selfie: bytes, templates: list[FaceTemplate]):
    """Compara 1:1 contra os templates ativos do proprio funcionario.

    1:1 e nao 1:N (decisao D3): o funcionario ja esta autenticado, entao
    sabemos contra quem comparar. Varrer a base inteira seria menos preciso e
    abriria a chance de casar com outra pessoa parecida.
    """
    try:
        embedding = await engine.extract_embedding(selfie)
    except FacialError as exc:
        raise TimeEntryError(exc.chave) from exc

    # Embeddings de modelos diferentes vivem em espacos vetoriais diferentes:
    # comparar um contra o outro nao da erro (a dimensao coincide), da um score
    # sem significado nenhum. Filtrar aqui e o que permite trocar de modelo sem
    # que os templates da geracao anterior contaminem a decisao — e o cenario
    # da fase edge, que toda a arquitetura antecipa.
    compativeis = [
        template
        for template in templates
        if template.model_name == embedding.model_name
        and template.model_version == embedding.model_version
    ]

    if not compativeis:
        raise StaleTemplateError()

    candidatos = [
        MatchCandidate(template_id=template.id, vector=template.embedding)
        for template in compativeis
    ]
    resultado = engine.verify_against_templates(
        embedding.vector,
        candidatos,
        match_threshold=settings.face_match_threshold,
        review_threshold=settings.face_review_threshold,
    )
    return resultado.score, resultado.outcome, resultado.template_id


# --------------------------------------------------------------------------
# Consulta e revisao
# --------------------------------------------------------------------------


def build_query(
    repo: TenantRepository,
    *,
    employee_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    status: TimeEntryStatus | None = None,
    location_method: LocationMethod | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
):
    """Consulta de pontos com os filtros do painel."""
    query = repo.query(TimeEntry)

    if employee_id is not None:
        query = query.where(TimeEntry.employee_id == employee_id)
    if site_id is not None:
        query = query.where(TimeEntry.site_id == site_id)
    if status is not None:
        query = query.where(TimeEntry.status == status)
    if location_method is not None:
        query = query.where(TimeEntry.location_method == location_method)
    if start is not None:
        query = query.where(TimeEntry.recorded_at >= start)
    if end is not None:
        query = query.where(TimeEntry.recorded_at <= end)

    return query.order_by(desc(TimeEntry.recorded_at))


async def review_entry(
    session: AsyncSession,
    entry: TimeEntry,
    *,
    reviewer_id: uuid.UUID,
    approved: bool,
    note: str | None,
    corrected_recorded_at: datetime | None = None,
) -> tuple[TimeEntry, datetime | None]:
    """Decisao do RH sobre uma pendencia.

    Quem revisou e quando ficam gravados: uma aprovacao sem autor nao serve
    como defesa em discussao trabalhista.

    Devolve tambem o horario anterior quando houve correcao, para o chamador
    registra-lo na trilha — sem isso, uma batida ajustada de 10:30 para 08:00
    ficaria indistinguivel de uma batida que sempre foi 08:00.
    """
    horario_anterior: datetime | None = None

    if corrected_recorded_at is not None:
        horario_anterior = entry.recorded_at
        entry.recorded_at = corrected_recorded_at

    entry.status = TimeEntryStatus.APPROVED if approved else TimeEntryStatus.REJECTED
    entry.reviewed_by_user_id = reviewer_id
    entry.reviewed_at = datetime.now(UTC)
    entry.review_note = note
    await session.flush()
    return entry, horario_anterior


async def load_selfie(storage: Storage, entry: TimeEntry) -> bytes | None:
    """Le a selfie de um registro, decifrando-a.

    None quando a imagem ja expirou pela politica de retencao (Etapa 11): o
    ponto sobrevive ao expurgo da foto, entao a ausencia e um estado normal e
    nao um erro.
    """
    if not entry.selfie_image_key:
        return None

    from app.services.storage import ObjectNotFoundError

    try:
        return await storage.load(entry.selfie_image_key)
    except ObjectNotFoundError:
        return None


async def load_employees_for(
    session: AsyncSession, entries: list[TimeEntry]
) -> dict[uuid.UUID, Employee]:
    """Carrega os funcionarios das linhas da listagem numa consulta so.

    Evita a consulta por linha que uma listagem de mil pontos geraria.
    """
    if not entries:
        return {}

    ids = {entry.employee_id for entry in entries}
    result = await session.execute(select(Employee).where(Employee.id.in_(ids)))
    return {employee.id: employee for employee in result.scalars().all()}


def default_period(days: int = 30) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(days=days), end
