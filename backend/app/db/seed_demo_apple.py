"""Cria o tenant de demonstracao usado na Beta App Review da Apple.

    fly ssh console --app waypoint-api -C "python -m app.db.seed_demo_apple"

Idempotente pelo slug.

**Por que este tenant precisa existir.** A revisao da Apple e feita por uma
pessoa num predio na California, e o app foi desenhado para recusar exatamente
essa pessoa: o rosto dela nao esta cadastrado (NO_MATCH -> REJECTED, em
`time_entry_decision`) e ela esta a milhares de quilometros de qualquer local
da empresa. Sem um tenant que a acomode, o revisor nao consegue exercitar a
funcionalidade principal — e "nao conseguimos avaliar o app" e uma das causas
mais comuns de reprovacao.

Tres afrouxamentos, todos escopados a este tenant:

1. **Limiar facial em -1.0.** Cosseno vive em [-1, 1] e `classify_score`
   aprova com `score >= match_threshold`, entao qualquer rosto passa. A coluna
   e por tenant justamente para que isso nao vaze para nenhuma empresa real.
2. **Geofence de 20.000 km**, que cobre o planeta. O elo do GPS valida de
   onde quer que o revisor esteja.
3. **Template facial sintetico.** O fluxo exige ao menos um template ativo
   (`NoFaceTemplatesError`); com o limiar em -1.0 o conteudo do vetor nao
   altera o desfecho, so precisa existir e ser do modelo em uso.

**A senha do funcionario demo nao e segredo**: ela vai escrita nas notas de
revisao da Apple. Por isso e legivel e fixa, ao contrario da senha do admin em
`seed_producao`, que e sorteada e impressa uma vez.

Este tenant nao deve receber gente de verdade. Ele aceita qualquer rosto.
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.facial import get_face_engine
from app.models import (
    Employee,
    EmployeeStatus,
    FaceTemplate,
    Site,
    Tenant,
)

SLUG = os.environ.get("DEMO_SLUG", "apple-review").strip()
MATRICULA = os.environ.get("DEMO_EMPLOYEE_CODE", "9001").strip()
SENHA = os.environ.get("DEMO_PASSWORD", "AppleReview2026").strip()

# Maior distancia possivel entre dois pontos da Terra e ~20.000 km. Com este
# raio, todo lugar do planeta esta "dentro do local".
RAIO_PLANETARIO_M = 20_000_000

EMBEDDING_DIM = 512


def _vetor_sintetico() -> list[float]:
    """Vetor unitario deterministico, so para haver um template ativo.

    Nao representa rosto nenhum. Com o limiar do tenant em -1.0 o score que
    ele produz e irrelevante para o desfecho — o que importa e que exista um
    template do mesmo modelo que a engine em uso, senao a batida morre antes
    da comparacao (StaleTemplateError).
    """
    valor = 1.0 / (EMBEDDING_DIM**0.5)
    return [valor] * EMBEDDING_DIM


async def semear(session: AsyncSession) -> None:
    if await session.scalar(select(Tenant).where(Tenant.slug == SLUG)):
        print(f"Tenant '{SLUG}' ja existe — nada a fazer.")
        return

    engine = get_face_engine()

    tenant = Tenant(
        name="Waypoint Demo (App Review)",
        slug=SLUG,
        timezone="America/New_York",
        # Aceita qualquer rosto. Ver o cabecalho deste arquivo.
        face_match_threshold=-1.0,
        face_review_threshold=-1.0,
    )
    session.add(tenant)
    await session.flush()

    site = Site(
        tenant_id=tenant.id,
        name="Demo Site",
        address="Demonstration site for App Review — accepts any location",
        latitude=0.0,
        longitude=0.0,
        geofence_radius_m=RAIO_PLANETARIO_M,
        timezone="America/New_York",
    )
    session.add(site)
    await session.flush()

    funcionario = Employee(
        tenant_id=tenant.id,
        external_code=MATRICULA,
        name="App Review Demo",
        job_title="Reviewer",
        password_hash=hash_password(SENHA),
        # False de proposito: trocar senha no primeiro acesso poria o revisor
        # numa tela que as notas nao explicam.
        must_change_password=False,
        status=EmployeeStatus.ACTIVE,
        default_site_id=site.id,
    )
    session.add(funcionario)
    await session.flush()

    session.add(
        FaceTemplate(
            tenant_id=tenant.id,
            employee_id=funcionario.id,
            embedding=_vetor_sintetico(),
            model_name=engine.name,
            model_version=engine.version,
            is_active=True,
        )
    )

    await session.commit()

    print("Tenant de demonstracao criado.\n")
    print("  Cole isto nas notas da Beta App Review:\n")
    print("    Company code: " + SLUG)
    print("    Employee ID:  " + MATRICULA)
    print("    Password:     " + SENHA)
    print("\n  O aparelho e pareado no primeiro login — a conta esta livre.")
    print("  Qualquer rosto e aceito e qualquer localizacao valida,")
    print("  apenas neste tenant.")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await semear(session)


if __name__ == "__main__":
    asyncio.run(main())
