"""Cadastro biometrico de um funcionario.

Transforma um punhado de fotos nos templates faciais contra os quais o ponto
sera conferido depois. E o ponto de entrada do dado mais sensivel do sistema,
entao concentra tres cuidados:

1. **Qualidade** — foto ruim gera template ruim, que gera falso negativo, e
   quem paga e o funcionario que nao consegue bater ponto.
2. **Coerencia** — todas as fotos precisam ser da mesma pessoa. Sem isso, uma
   troca acidental de arquivo no painel contaminaria a base silenciosamente e
   passaria a aceitar duas pessoas como uma so.
3. **Consentimento** — sem base legal registrada nao ha tratamento de dado
   biometrico.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.messages import IDIOMA_PADRAO, Msg, traduzir
from app.db.repository import TenantRepository
from app.facial import FacialError, cosine_similarity
from app.facial.base import FaceEmbedding
from app.facial.imaging import inspect_image
from app.facial.runner import AsyncFaceEngine
from app.models import Consent, Employee, FaceTemplate
from app.models.enums import ConsentType
from app.schemas.face_template import ConsentDeclaration, RejectedImage
from app.services.storage import Storage

# Prefixo das fotos de referencia no storage.
FACE_STORAGE_PREFIX = "faces"


class EnrollmentError(Exception):
    """Falha que impede o cadastro biometrico inteiro.

    Carrega a chave da mensagem e os parametros dela, em vez do texto: quem
    levanta o erro nao sabe o idioma de quem esta no painel. A borda HTTP
    resolve com `traduzir(exc.chave, idioma, **exc.parametros)`.

    O `str(exc)` continua legivel — em ingles, fixo — porque e o que vai para
    o log, e log traduzido e log que nao se consegue procurar.
    """

    chave: Msg = Msg.IMAGEM_ILEGIVEL

    def __init__(self, **parametros: object) -> None:
        self.parametros = parametros
        super().__init__(traduzir(self.chave, IDIOMA_PADRAO, **parametros))


class ConsentRequiredError(EnrollmentError):
    chave = Msg.CONSENTIMENTO_OBRIGATORIO


class NotEnoughImagesError(EnrollmentError):
    chave = Msg.FOTOS_DE_MENOS


class TooManyImagesError(EnrollmentError):
    chave = Msg.FOTOS_DE_MAIS


class NotEnoughUsableImagesError(EnrollmentError):
    """Chegaram fotos suficientes, mas poucas serviram.

    Guarda a lista de recusas para a borda HTTP remontar o "Problemas: ..." no
    idioma de quem pediu — o texto ja embutido em `parametros` esta em ingles.
    """

    chave = Msg.POUCAS_FOTOS_COM_QUALIDADE

    def __init__(self, *, rejected: list[RejectedImage], **parametros: object) -> None:
        super().__init__(**parametros)
        self.rejected = rejected


class InconsistentImagesError(EnrollmentError):
    """As fotos enviadas nao sao todas da mesma pessoa."""

    chave = Msg.PESSOAS_DIFERENTES

    def __init__(self, *, worst_score: float, **parametros: object) -> None:
        super().__init__(score=f"{worst_score:.2f}", **parametros)
        self.worst_score = worst_score


@dataclass
class UploadedImage:
    filename: str
    content: bytes


@dataclass
class EnrollmentOutcome:
    templates: list[FaceTemplate]
    rejected: list[RejectedImage]
    deactivated_previous: int
    consent: Consent


async def enroll_face(
    session: AsyncSession,
    repo: TenantRepository,
    engine: AsyncFaceEngine,
    storage: Storage,
    *,
    employee: Employee,
    images: list[UploadedImage],
    consent: ConsentDeclaration,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> EnrollmentOutcome:
    """Cadastra o rosto do funcionario a partir das fotos enviadas.

    Substitui o conjunto ativo: os templates anteriores sao desativados, nunca
    apagados — o historico de pontos aponta para eles e precisa continuar
    auditavel.
    """
    if not consent.granted:
        raise ConsentRequiredError()

    _validate_count(len(images))

    accepted, rejected = await _extract_embeddings(engine, images)

    # Contado sobre as fotos que passaram na qualidade: se sobrarem menos que o
    # minimo, o cadastro nao se sustenta mesmo que o envio tivesse quantidade.
    if len(accepted) < settings.face_min_enrollment_images:
        raise NotEnoughUsableImagesError(
            accepted=len(accepted),
            total=len(images),
            minimum=settings.face_min_enrollment_images,
            problems=resumir_recusas(rejected, IDIOMA_PADRAO),
            rejected=rejected,
        )

    _ensure_same_person([embedding for _, embedding in accepted])

    deactivated = await _deactivate_previous(session, employee)

    templates: list[FaceTemplate] = []
    for image, embedding in accepted:
        image_key = await storage.save(
            image.content,
            prefix=FACE_STORAGE_PREFIX,
            image_format=inspect_image(image.content).format,
        )
        template = FaceTemplate(
            employee_id=employee.id,
            embedding=list(embedding.vector),
            model_name=embedding.model_name,
            model_version=embedding.model_version,
            quality_score=embedding.quality.score,
            source_image_key=image_key,
            is_active=True,
        )
        repo.add(template)
        templates.append(template)

    consent_record = Consent(
        tenant_id=employee.tenant_id,
        employee_id=employee.id,
        consent_type=ConsentType.BIOMETRIC,
        policy_version=consent.policy_version,
        granted_at=datetime.now(UTC),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(consent_record)

    await session.flush()

    return EnrollmentOutcome(
        templates=templates,
        rejected=rejected,
        deactivated_previous=deactivated,
        consent=consent_record,
    )


def _validate_count(quantity: int) -> None:
    minimum = settings.face_min_enrollment_images
    maximum = settings.face_max_enrollment_images

    if quantity < minimum:
        raise NotEnoughImagesError(minimum=minimum, quantity=quantity)
    if quantity > maximum:
        raise TooManyImagesError(maximum=maximum, quantity=quantity)


async def _extract_embeddings(
    engine: AsyncFaceEngine,
    images: list[UploadedImage],
) -> tuple[list[tuple[UploadedImage, FaceEmbedding]], list[RejectedImage]]:
    """Extrai o embedding de cada foto, separando as que nao servem.

    Uma foto ruim nao derruba o envio inteiro: o RH recebe de volta quais
    falharam e por que, e pode reenviar so aquelas.
    """
    accepted: list[tuple[UploadedImage, FaceEmbedding]] = []
    rejected: list[RejectedImage] = []

    for image in images:
        try:
            embedding = await engine.extract_embedding(image.content)
        except FacialError as exc:
            rejected.append(RejectedImage(filename=image.filename, reason=exc.chave.value))
            continue

        if not embedding.quality.is_acceptable:
            rejected.append(
                RejectedImage(
                    filename=image.filename,
                    reason=Msg.QUALIDADE_INSUFICIENTE.value,
                    issues=list(embedding.quality.issues),
                )
            )
            continue

        accepted.append((image, embedding))

    return accepted, rejected


def _ensure_same_person(embeddings: list[FaceEmbedding]) -> None:
    """Confere que todas as fotos aceitas sao da mesma pessoa.

    Compara todos os pares. Fotos tiradas em sequencia no cadastro deveriam
    bater com folga; um par abaixo do limiar significa que alguma foto e de
    outra pessoa — arquivo trocado no painel, ou alguem ao fundo entrando no
    lugar do titular.
    """
    threshold = settings.face_match_threshold

    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            score = cosine_similarity(embeddings[i].vector, embeddings[j].vector)
            if score < threshold:
                raise InconsistentImagesError(worst_score=score)


async def _deactivate_previous(session: AsyncSession, employee: Employee) -> int:
    """Desativa os templates ativos atuais. Nunca apaga.

    Os registros de ponto referenciam o template que aprovou cada batida; um
    delete quebraria a auditoria de meses atras.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        update(FaceTemplate)
        .where(
            FaceTemplate.tenant_id == employee.tenant_id,
            FaceTemplate.employee_id == employee.id,
            FaceTemplate.is_active.is_(True),
        )
        .values(is_active=False, deactivated_at=now)
    )
    return result.rowcount or 0


async def deactivate_template(session: AsyncSession, template: FaceTemplate) -> FaceTemplate:
    template.is_active = False
    template.deactivated_at = datetime.now(UTC)
    await session.flush()
    return template


async def list_templates(
    repo: TenantRepository, employee_id: uuid.UUID, *, include_inactive: bool = False
) -> list[FaceTemplate]:
    query = repo.query(FaceTemplate).where(FaceTemplate.employee_id == employee_id)
    if not include_inactive:
        query = query.where(FaceTemplate.is_active.is_(True))

    result = await repo.session.execute(query.order_by(FaceTemplate.created_at.desc()))
    return list(result.scalars().all())


async def load_active_templates(session: AsyncSession, employee: Employee) -> list[FaceTemplate]:
    """Templates ativos de um funcionario, para a conferencia do ponto (Etapa 7)."""
    result = await session.execute(
        select(FaceTemplate).where(
            FaceTemplate.tenant_id == employee.tenant_id,
            FaceTemplate.employee_id == employee.id,
            FaceTemplate.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


# Codigo de problema -> chave da orientacao acionavel. Dizer "qualidade
# insuficiente" nao informa a ninguem se deve chegar mais perto, acender a luz
# ou firmar a mao — e essa mensagem e a unica coisa que a pessoa ve quando o
# cadastro inteiro e recusado.
ORIENTACAO_POR_PROBLEMA: dict[str, Msg] = {
    "blurry": Msg.ORIENTACAO_DESFOCADA,
    "face_too_small": Msg.ORIENTACAO_ROSTO_PEQUENO,
    "face_too_far": Msg.ORIENTACAO_ROSTO_LONGE,
    "face_cropped": Msg.ORIENTACAO_ROSTO_CORTADO,
    "low_detection_confidence": Msg.ORIENTACAO_POUCA_CONFIANCA,
}


def resumir_recusas(rejected: list[RejectedImage], idioma: str) -> str:
    """Descreve foto a foto por que cada uma foi recusada.

    Publica porque a borda HTTP a chama de novo, no idioma de quem pediu: o
    texto montado no `raise` fica em ingles, que e o que serve para o log.
    """
    if not rejected:
        return "—"

    partes = []
    for item in rejected:
        if item.issues:
            detalhe = "; ".join(
                traduzir(ORIENTACAO_POR_PROBLEMA[i], idioma) if i in ORIENTACAO_POR_PROBLEMA else i
                for i in item.issues
            )
        else:
            # `reason` e chave do catalogo, nao prosa — ver `RejectedImage`.
            detalhe = traduzir(Msg(item.reason), idioma)
        partes.append(f"{item.filename} ({detalhe})")
    return " · ".join(partes)
