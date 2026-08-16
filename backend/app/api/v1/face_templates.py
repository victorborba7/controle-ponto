"""Cadastro biometrico de funcionarios.

Nenhuma resposta destes endpoints carrega o embedding. O painel precisa saber
que o cadastro existe, com que qualidade e desde quando — nao precisa do vetor,
e o vetor e dado sensivel que nao tem por que trafegar.
"""

import uuid

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

from app.api.deps import (
    CurrentAdmin,
    FaceEngineDep,
    Locale,
    SessionDep,
    StorageDep,
    TenantRepo,
    erro_http,
    require_roles,
)
from app.core.messages import Msg
from app.core.net import client_ip
from app.facial.imaging import MAX_IMAGE_BYTES
from app.models import Employee, FaceTemplate
from app.models.enums import AuditAction, UserRole
from app.schemas.face_template import (
    ConsentDeclaration,
    EnrollmentResult,
    FaceTemplateList,
    FaceTemplateSummary,
)
from app.services import audit
from app.services import enrollment as enrollment_service
from app.services.enrollment import UploadedImage

router = APIRouter(prefix="/employees/{employee_id}/face-templates", tags=["biometria"])

# Consultar e papel de qualquer perfil do painel; cadastrar biometria nao e de
# quem so tem acesso de leitura.
ESCRITA = [Depends(require_roles(UserRole.OWNER, UserRole.HR))]


async def _get_employee_or_404(repo: TenantRepo, employee_id: uuid.UUID, idioma: str) -> Employee:
    employee = await repo.get(Employee, employee_id)
    if employee is None:
        raise erro_http(status.HTTP_404_NOT_FOUND, Msg.FUNCIONARIO_NAO_ENCONTRADO, idioma)
    return employee


async def _read_upload(upload: UploadFile, idioma: str) -> UploadedImage:
    """Le o arquivo com teto de tamanho.

    O teto e aplicado durante a leitura, e nao depois: deixar um upload de
    centenas de MB entrar inteiro na memoria para so entao recusar seria o
    proprio problema.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise erro_http(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                Msg.FOTO_NOMEADA_GRANDE_DEMAIS,
                idioma,
                filename=upload.filename,
                limit=MAX_IMAGE_BYTES // (1024 * 1024),
            )
        chunks.append(chunk)

    return UploadedImage(filename=upload.filename or "unnamed", content=b"".join(chunks))


@router.post(
    "",
    response_model=EnrollmentResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITA,
)
async def enroll(
    employee_id: uuid.UUID,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    engine: FaceEngineDep,
    storage: StorageDep,
    request: Request,
    idioma: Locale,
    images: list[UploadFile] = File(..., description="De 3 a 5 fotos do rosto do funcionario"),
    consent_policy_version: str = Form(..., description="Versao do termo de consentimento aceito"),
    consent_granted: bool = Form(
        ..., description="Confirma que o funcionario consentiu com o uso da biometria"
    ),
) -> EnrollmentResult:
    """Cadastra o rosto do funcionario.

    Substitui o conjunto ativo: os templates anteriores sao desativados (nunca
    apagados, porque o historico de pontos aponta para eles).

    Multipart, e nao JSON com base64: base64 infla o payload em 33% e forcaria
    carregar tudo na memoria de uma vez.
    """
    employee = await _get_employee_or_404(repo, employee_id, idioma)

    try:
        consent = ConsentDeclaration(policy_version=consent_policy_version, granted=consent_granted)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc

    uploads = [await _read_upload(image, idioma) for image in images]

    try:
        outcome = await enrollment_service.enroll_face(
            session,
            repo,
            engine,
            storage,
            employee=employee,
            images=uploads,
            consent=consent,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:400] or None,
        )
    except enrollment_service.ConsentRequiredError as exc:
        raise erro_http(status.HTTP_403_FORBIDDEN, exc.chave, idioma, **exc.parametros) from exc
    except enrollment_service.NotEnoughUsableImagesError as exc:
        # O "Problemas: ..." e remontado aqui: o texto que veio no `raise` esta
        # em ingles, que serve para o log e nao para a tela do RH.
        raise erro_http(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.chave,
            idioma,
            **{
                **exc.parametros,
                "problems": enrollment_service.resumir_recusas(exc.rejected, idioma),
            },
        ) from exc
    except enrollment_service.EnrollmentError as exc:
        raise erro_http(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc.chave, idioma, **exc.parametros
        ) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CONSENT_GRANTED,
        entity_type="face_template",
        entity_id=employee.id,
        payload={
            "templates_criados": len(outcome.templates),
            "templates_desativados": outcome.deactivated_previous,
            "fotos_recusadas": len(outcome.rejected),
            "versao_do_termo": consent.policy_version,
        },
        description=f"Cadastro biometrico de {employee.name}",
        ip_address=client_ip(request),
    )

    return EnrollmentResult(
        employee_id=employee.id,
        created=[FaceTemplateSummary.model_validate(t) for t in outcome.templates],
        rejected=outcome.rejected,
        deactivated_previous=outcome.deactivated_previous,
        consent_id=outcome.consent.id,
    )


@router.get("", response_model=FaceTemplateList)
async def list_templates(
    employee_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
    idioma: Locale,
    include_inactive: bool = Query(default=False),
) -> FaceTemplateList:
    await _get_employee_or_404(repo, employee_id, idioma)
    templates = await enrollment_service.list_templates(
        repo, employee_id, include_inactive=include_inactive
    )
    return FaceTemplateList(
        items=[FaceTemplateSummary.model_validate(t) for t in templates],
        total=len(templates),
    )


@router.delete("/{template_id}", response_model=FaceTemplateSummary, dependencies=ESCRITA)
async def deactivate_template(
    employee_id: uuid.UUID,
    template_id: uuid.UUID,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
    idioma: Locale,
) -> FaceTemplateSummary:
    """Desativa um template. O registro permanece, para auditoria.

    DELETE no verbo por ser a intencao do chamador, mas a exclusao e logica: os
    pontos ja aprovados apontam para este template e precisam continuar
    explicaveis.
    """
    await _get_employee_or_404(repo, employee_id, idioma)

    template = await repo.get(FaceTemplate, template_id)
    if template is None or template.employee_id != employee_id:
        raise erro_http(status.HTTP_404_NOT_FOUND, Msg.TEMPLATE_NAO_ENCONTRADO, idioma)

    await enrollment_service.deactivate_template(session, template)

    await audit.record_for(
        session,
        principal,
        action=AuditAction.DELETE,
        entity_type="face_template",
        entity_id=template.id,
        description="Template facial desativado",
        ip_address=client_ip(request),
    )

    return FaceTemplateSummary.model_validate(template)
