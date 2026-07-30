"""Registro e consulta de pontos.

`POST` e do app do funcionario; consulta e revisao sao do painel. Sao publicos
diferentes de proposito: bater ponto e ato pessoal, e um administrador com
token valido nao pode registrar presenca por ninguem.
"""

import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.deps import (
    CurrentAdmin,
    CurrentEmployee,
    FaceEngineDep,
    SessionDep,
    StorageDep,
    TenantRepo,
    require_roles,
)
from app.facial.imaging import MAX_IMAGE_BYTES
from app.models import Device, Employee, Site, TimeEntry
from app.models.enums import (
    AuditAction,
    EntryType,
    LocationMethod,
    TimeEntryStatus,
    UserRole,
)
from app.schemas.evidence import LocationEvidence
from app.schemas.time_entry import (
    MyTimeEntryList,
    TimeEntryCreated,
    TimeEntryList,
    TimeEntryReview,
    TimeEntrySummary,
    TimeEntryWithEmployee,
)
from app.services import audit
from app.services import time_entry as service

router = APIRouter(prefix="/time-entries", tags=["ponto"])

REVISAO = [Depends(require_roles(UserRole.OWNER, UserRole.HR))]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _read_selfie(upload: UploadFile) -> bytes:
    """Le a selfie com teto de tamanho aplicado durante a leitura."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"A foto excede o limite de {MAX_IMAGE_BYTES // (1024 * 1024)} MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# --------------------------------------------------------------------------
# Bater ponto
# --------------------------------------------------------------------------


@router.post("", response_model=TimeEntryCreated, status_code=status.HTTP_201_CREATED)
async def punch(
    principal: CurrentEmployee,
    repo: TenantRepo,
    session: SessionDep,
    engine: FaceEngineDep,
    storage: StorageDep,
    request: Request,
    selfie: UploadFile = File(..., description="Foto do rosto no momento da batida"),
    evidence: str = Form(
        ...,
        description="JSON com os sinais observados: beacons, redes Wi-Fi e GPS",
    ),
    entry_type: EntryType | None = Form(
        default=None,
        description="Entrada ou saida. Se omitido, e deduzido da ultima batida.",
    ),
    idempotency_key: str | None = Form(
        default=None,
        max_length=80,
        description="Chave do app para que um reenvio nao vire dois registros",
    ),
    client_recorded_at: datetime | None = Form(
        default=None, description="Horario do aparelho, para deteccao de divergencia"
    ),
) -> TimeEntryCreated:
    """Registra o ponto do funcionario autenticado.

    Multipart porque a selfie e binaria; a evidencia de localizacao vem como
    JSON num campo de formulario.
    """
    try:
        parsed_evidence = LocationEvidence.model_validate_json(evidence)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"campo": "evidence", "erros": exc.errors()},
        ) from exc

    employee = await repo.get(Employee, principal.subject_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Funcionario nao encontrado"
        )

    device = (
        await repo.get(Device, principal.device_id) if principal.device_id else None
    )
    selfie_bytes = await _read_selfie(selfie)

    try:
        resultado = await service.punch(
            session,
            repo,
            engine,
            storage,
            employee=employee,
            device=device,
            selfie=selfie_bytes,
            evidence=parsed_evidence,
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            client_recorded_at=client_recorded_at,
        )
    except service.FaceRejectedError as exc:
        # A tentativa fica na trilha mesmo sem virar registro de ponto: e o que
        # permite investigar depois quem tentou bater ponto por quem.
        await audit.record_for(
            session,
            principal,
            action=AuditAction.TIME_ENTRY,
            entity_type="time_entry",
            payload={"recusado": True, "face_score": exc.score},
            description=str(exc),
            ip_address=_client_ip(request),
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.user_message
        ) from exc
    except service.TooSoonError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Voce acabou de bater o ponto. Aguarde um momento.",
        ) from exc
    except service.DeviceNotTrustedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=exc.user_message
        ) from exc
    except service.NoFaceTemplatesError as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED, detail=exc.user_message
        ) from exc
    except service.TimeEntryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.user_message
        ) from exc

    if not resultado.duplicate:
        await audit.record_for(
            session,
            principal,
            action=AuditAction.TIME_ENTRY,
            entity_type="time_entry",
            entity_id=resultado.entry.id,
            payload={
                "tipo": resultado.entry.entry_type.value,
                "status": resultado.entry.status.value,
                "metodo": resultado.entry.location_method.value,
                "face_score": resultado.entry.face_match_score,
            },
            description=resultado.decision.reason,
            ip_address=_client_ip(request),
        )

    return TimeEntryCreated(
        entry=TimeEntrySummary.model_validate(resultado.entry),
        message=resultado.decision.message,
        duplicate=resultado.duplicate,
    )


# --------------------------------------------------------------------------
# Historico do proprio funcionario
# --------------------------------------------------------------------------


@router.get("/me", response_model=MyTimeEntryList)
async def my_entries(
    principal: CurrentEmployee,
    repo: TenantRepo,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MyTimeEntryList:
    """Registros do proprio funcionario.

    Endpoint separado do de consulta do RH, e nao o mesmo com filtro: assim
    nao existe caminho em que um parametro mal validado exponha o ponto dos
    colegas.
    """
    query = service.build_query(repo, employee_id=principal.subject_id)

    total = await repo.session.scalar(
        select(func.count()).select_from(query.subquery())
    )
    result = await repo.session.execute(query.limit(limit).offset(offset))

    return MyTimeEntryList(
        items=[TimeEntrySummary.model_validate(e) for e in result.scalars().all()],
        total=total or 0,
    )


# --------------------------------------------------------------------------
# Consulta do painel
# --------------------------------------------------------------------------


@router.get("", response_model=TimeEntryList)
async def list_entries(
    _: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    employee_id: uuid.UUID | None = Query(default=None),
    site_id: uuid.UUID | None = Query(default=None),
    entry_status: TimeEntryStatus | None = Query(default=None, alias="status"),
    location_method: LocationMethod | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TimeEntryList:
    """Pontos da empresa, com os filtros do painel."""
    query = service.build_query(
        repo,
        employee_id=employee_id,
        site_id=site_id,
        status=entry_status,
        location_method=location_method,
        start=start,
        end=end,
    )

    total = await repo.session.scalar(
        select(func.count()).select_from(query.subquery())
    )
    result = await repo.session.execute(query.limit(limit).offset(offset))
    entries = list(result.scalars().all())

    employees = await service.load_employees_for(session, entries)
    sites = await _load_sites(repo, entries)

    return TimeEntryList(
        items=[_with_names(entry, employees, sites) for entry in entries],
        total=total or 0,
    )


@router.get("/{entry_id}", response_model=TimeEntryWithEmployee)
async def get_entry(
    entry_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
) -> TimeEntryWithEmployee:
    entry = await _entry_or_404(repo, entry_id)
    employees = await service.load_employees_for(session, [entry])
    sites = await _load_sites(repo, [entry])
    return _with_names(entry, employees, sites)


@router.patch(
    "/{entry_id}/review", response_model=TimeEntryWithEmployee, dependencies=REVISAO
)
async def review(
    entry_id: uuid.UUID,
    payload: TimeEntryReview,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> TimeEntryWithEmployee:
    """Aprova ou rejeita uma pendencia.

    Quem revisou e quando ficam gravados no proprio registro: uma aprovacao sem
    autor nao serve de defesa em discussao trabalhista.
    """
    entry = await _entry_or_404(repo, entry_id)

    if entry.status is not TimeEntryStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este registro nao esta pendente (situacao atual: {entry.status.value})",
        )

    await service.review_entry(
        session,
        entry,
        reviewer_id=principal.subject_id,
        approved=payload.approved,
        note=payload.note,
    )

    await audit.record_for(
        session,
        principal,
        action=AuditAction.REVIEW,
        entity_type="time_entry",
        entity_id=entry.id,
        payload={"aprovado": payload.approved},
        description=payload.note,
        ip_address=_client_ip(request),
    )

    employees = await service.load_employees_for(session, [entry])
    sites = await _load_sites(repo, [entry])
    return _with_names(entry, employees, sites)


# --------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------


async def _entry_or_404(repo: TenantRepo, entry_id: uuid.UUID) -> TimeEntry:
    entry = await repo.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Registro nao encontrado"
        )
    return entry


async def _load_sites(
    repo: TenantRepo, entries: list[TimeEntry]
) -> dict[uuid.UUID, Site]:
    ids = {entry.site_id for entry in entries if entry.site_id}
    if not ids:
        return {}

    result = await repo.session.execute(repo.query(Site).where(Site.id.in_(ids)))
    return {site.id: site for site in result.scalars().all()}


def _with_names(
    entry: TimeEntry,
    employees: dict[uuid.UUID, Employee],
    sites: dict[uuid.UUID, Site],
) -> TimeEntryWithEmployee:
    employee = employees.get(entry.employee_id)
    site = sites.get(entry.site_id) if entry.site_id else None

    return TimeEntryWithEmployee(
        **TimeEntrySummary.model_validate(entry).model_dump(),
        # "(removido)" e nao um erro: o funcionario pode ter sido excluido pelo
        # direito ao esquecimento (Etapa 11), e o ponto dele sobrevive por
        # obrigacao trabalhista.
        employee_name=employee.name if employee else "(removido)",
        employee_code=employee.external_code if employee else "-",
        site_name=site.name if site else None,
    )
