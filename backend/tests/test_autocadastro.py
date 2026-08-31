"""Autocadastro biometrico: o funcionario cadastra o proprio rosto pelo app.

O que estes testes protegem nao e o caminho feliz — esse e o mesmo
`enroll_face` que o RH ja usava. E a **guarda**: autocadastro so na primeira
vez, e so de si mesmo.

Sem ela, uma credencial vazada viraria controle permanente da conta: bastaria
cadastrar o proprio rosto por cima do existente, e todas as batidas seguintes
casariam com score alto, sem sinal nenhum de fraude. A decisao de produto foi
aceitar esse risco na primeira vez, em troca de o recem-contratado nao precisar
ir ate o RH; nao foi estende-lo a quem ja esta cadastrado.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import Msg, traduzir
from app.facial.stub import stub_image, stub_image_variant
from app.models import AuditLog, Consent, FaceTemplate
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    create_admin,
    create_employee,
    create_tenant,
    device_payload,
)

PESSOA = (200, 30, 30)
OUTRA_PESSOA = (30, 30, 200)
URL = "/api/v1/me/face-templates"


def _fotos(cor: tuple[int, int, int], quantidade: int = 3) -> list[tuple[str, tuple]]:
    arquivos = [("images", ("f1.png", stub_image(cor), "image/png"))]
    for indice in range(1, quantidade):
        arquivos.append(
            (
                "images",
                (
                    f"f{indice + 1}.png",
                    stub_image_variant(cor, shift=indice * 4),
                    "image/png",
                ),
            )
        )
    return arquivos


def _consentimento(granted: bool = True) -> dict[str, str]:
    return {
        "consent_policy_version": "2026.1",
        "consent_granted": "true" if granted else "false",
    }


@pytest.fixture
async def app_do_funcionario(client: AsyncClient, db: AsyncSession) -> dict:
    """Funcionario logado no app e **sem** rosto cadastrado."""
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com")
    funcionario = await create_employee(db, tenant, external_code="0001", name="Joao")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload("celular-do-joao"),
        },
    )
    assert login.status_code == 200, login.text

    return {
        "tenant": tenant,
        "funcionario": funcionario,
        # O id vai solto tambem: requisicoes que terminam em erro provocam
        # rollback na sessao compartilhada do teste, e ler `funcionario.id`
        # depois disso tenta recarregar do banco fora do contexto async.
        "funcionario_id": funcionario.id,
        "headers": auth_header(login.json()["tokens"]),
    }


# --------------------------------------------------------------------------
# Caminho feliz
# --------------------------------------------------------------------------


async def test_funcionario_cadastra_o_proprio_rosto(
    client: AsyncClient, app_do_funcionario: dict
):
    resposta = await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert len(corpo["created"]) == 3
    assert corpo["employee_id"] == str(app_do_funcionario["funcionario_id"])


async def test_templates_ficam_ativos_de_imediato(
    client: AsyncClient, db: AsyncSession, app_do_funcionario: dict
):
    """Decisao de produto: vale na hora, sem conferencia do RH."""
    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    templates = (
        await db.scalars(
            select(FaceTemplate).where(
                FaceTemplate.employee_id == app_do_funcionario["funcionario_id"]
            )
        )
    ).all()
    assert len(templates) == 3
    assert all(t.is_active for t in templates)


async def test_consentimento_do_proprio_titular_e_registrado(
    client: AsyncClient, db: AsyncSession, app_do_funcionario: dict
):
    """O aceite vale mais aqui: quem leu o termo foi o dono do dado."""
    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    consentimentos = (
        await db.scalars(
            select(Consent).where(
                Consent.employee_id == app_do_funcionario["funcionario_id"]
            )
        )
    ).all()
    assert consentimentos, "o cadastro tem de gravar o consentimento"


async def test_auditoria_distingue_autocadastro_de_cadastro_pelo_rh(
    client: AsyncClient, db: AsyncSession, app_do_funcionario: dict
):
    """Numa contestacao, "o RH viu esta pessoa" e "ela se cadastrou sozinha"
    sao fatos diferentes, e a trilha precisa separar os dois."""
    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    registros = (await db.scalars(select(AuditLog))).all()
    autocadastros = [r for r in registros if (r.payload or {}).get("autocadastro")]
    assert len(autocadastros) == 1


# --------------------------------------------------------------------------
# A guarda — o motivo deste arquivo existir
# --------------------------------------------------------------------------


async def test_segundo_cadastro_e_recusado(client: AsyncClient, app_do_funcionario: dict):
    primeiro = await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )
    assert primeiro.status_code == 201

    segundo = await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(OUTRA_PESSOA),
        data=_consentimento(),
    )

    assert segundo.status_code == 409
    assert segundo.json()["detail"] == traduzir(Msg.ROSTO_JA_CADASTRADO, "en")


async def test_recusa_nao_altera_o_cadastro_existente(
    client: AsyncClient, db: AsyncSession, app_do_funcionario: dict
):
    """A tentativa recusada nao pode desativar nem substituir nada.

    E o cenario do ataque: quem tem a senha tenta trocar o rosto pelo proprio.
    Recusar com 409 e insuficiente se o efeito colateral ja tiver acontecido.
    """
    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )
    # Os ids sao extraidos ja: guardar os objetos e le-los depois do proximo
    # commit dispara refresh preguicoso fora do contexto async (MissingGreenlet).
    antes = {
        t.id
        for t in (
            await db.scalars(
                select(FaceTemplate).where(
                    FaceTemplate.employee_id == app_do_funcionario["funcionario_id"],
                    FaceTemplate.is_active.is_(True),
                )
            )
        ).all()
    }

    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(OUTRA_PESSOA),
        data=_consentimento(),
    )

    depois = {
        t.id
        for t in (
            await db.scalars(
                select(FaceTemplate).where(
                    FaceTemplate.employee_id == app_do_funcionario["funcionario_id"],
                    FaceTemplate.is_active.is_(True),
                )
            )
        ).all()
    }
    assert antes == depois


async def test_token_do_painel_nao_serve(client: AsyncClient, db: AsyncSession):
    """Rota do app: quem tem token de admin usa o caminho com employee_id."""
    tenant = await create_tenant(db, slug="beta")
    await create_admin(db, tenant, email="rh@beta.com")
    await db.commit()

    from tests.conftest import login_admin

    login = await login_admin(client, tenant, "rh@beta.com")

    resposta = await client.post(
        URL,
        headers=auth_header(login["tokens"]),
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    assert resposta.status_code == 403


async def test_sem_token_e_recusado(client: AsyncClient):
    resposta = await client.post(URL, files=_fotos(PESSOA), data=_consentimento())
    assert resposta.status_code == 401


async def test_sem_consentimento_nao_cadastra(client: AsyncClient, app_do_funcionario: dict):
    resposta = await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(granted=False),
    )
    assert resposta.status_code == 403


# --------------------------------------------------------------------------
# O sinal que manda o app para a tela certa
# --------------------------------------------------------------------------
#
# `face_enrolled` e a unica coisa que o app consulta para decidir entre cadastro
# do rosto e batida de ponto. Ninguem cobria esse campo, e um iPhone abriu
# direto na batida sem rosto cadastrado. O caminho do autocadastro estava certo;
# o que faltava era garantir que o sinal acompanha o estado real.


async def test_login_avisa_que_falta_rosto(client: AsyncClient, app_do_funcionario: dict):
    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload("celular-do-joao"),
        },
    )

    assert login.status_code == 200, login.text
    assert login.json()["employee"]["face_enrolled"] is False


async def test_me_avisa_que_falta_rosto(client: AsyncClient, app_do_funcionario: dict):
    """O app reconfere aqui na abertura, porque o perfil guardado envelhece."""
    resposta = await client.get("/api/v1/auth/me", headers=app_do_funcionario["headers"])

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["face_enrolled"] is False


async def test_depois_do_cadastro_o_sinal_vira(client: AsyncClient, app_do_funcionario: dict):
    await client.post(
        URL,
        headers=app_do_funcionario["headers"],
        files=_fotos(PESSOA),
        data=_consentimento(),
    )

    resposta = await client.get("/api/v1/auth/me", headers=app_do_funcionario["headers"])
    assert resposta.json()["face_enrolled"] is True
