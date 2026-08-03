"""Cadastro biometrico: qualidade, coerencia entre fotos e consentimento.

Usa a engine stub, em que a cor da imagem e a identidade — assim os cenarios
("tres fotos da mesma pessoa", "uma foto de outra pessoa no meio") ficam
explicitos no teste em vez de dependerem de fotos reais versionadas.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import Msg, traduzir
from app.facial.stub import stub_image, stub_image_variant, stub_image_with_faces
from app.models import Consent, FaceTemplate
from app.models.enums import ConsentType
from app.services.storage import LocalStorage
from tests.conftest import (
    auth_header,
    create_admin,
    create_employee,
    create_tenant,
    login_admin,
)

PESSOA_A = (200, 30, 30)
PESSOA_B = (30, 30, 200)

VERSAO_DO_TERMO = "2026.1"


def _fotos_da_mesma_pessoa(quantidade: int = 3) -> list[tuple[str, bytes, str]]:
    """Fotos distintas da mesma pessoa, no formato multipart do httpx."""
    arquivos = [("images", ("foto-1.png", stub_image(PESSOA_A), "image/png"))]
    for indice in range(1, quantidade):
        arquivos.append(
            (
                "images",
                (
                    f"foto-{indice + 1}.png",
                    stub_image_variant(PESSOA_A, shift=indice * 4),
                    "image/png",
                ),
            )
        )
    return arquivos


def _consentimento(granted: bool = True) -> dict[str, str]:
    return {
        "consent_policy_version": VERSAO_DO_TERMO,
        "consent_granted": "true" if granted else "false",
    }


@pytest.fixture
async def cenario(client: AsyncClient, db: AsyncSession):
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com")
    funcionario = await create_employee(db, tenant, external_code="0001", name="Joao")
    await db.commit()

    login = await login_admin(client, tenant, "rh@acme.com")
    return {
        "tenant": tenant,
        "funcionario": funcionario,
        "headers": auth_header(login["tokens"]),
        "url": f"/api/v1/employees/{funcionario.id}/face-templates",
    }


# --------------------------------------------------------------------------
# Caminho feliz — o criterio de pronto da etapa
# --------------------------------------------------------------------------


async def test_cadastrar_tres_fotos(client: AsyncClient, cenario: dict):
    response = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    assert response.status_code == 201, response.text
    corpo = response.json()

    assert len(corpo["created"]) == 3
    assert corpo["rejected"] == []
    assert corpo["deactivated_previous"] == 0
    assert corpo["consent_id"]

    for template in corpo["created"]:
        assert template["is_active"] is True
        assert template["model_name"] == "stub"
        assert 0.0 <= template["quality_score"] <= 1.0


async def test_templates_ficam_persistidos_com_o_embedding(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    templates = (await db.execute(select(FaceTemplate))).scalars().all()

    assert len(templates) == 3
    for template in templates:
        assert len(template.embedding) == 512
        assert template.source_image_key.startswith("faces/")
        assert template.tenant_id == cenario["tenant"].id


async def test_contador_do_funcionario_reflete_o_cadastro(client: AsyncClient, cenario: dict):
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    ficha = await client.get(
        f"/api/v1/employees/{cenario['funcionario'].id}", headers=cenario["headers"]
    )
    assert ficha.json()["active_face_templates"] == 3


async def test_cinco_fotos_tambem_e_aceito(client: AsyncClient, cenario: dict):
    response = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(5),
        data=_consentimento(),
    )
    assert response.status_code == 201
    assert len(response.json()["created"]) == 5


# --------------------------------------------------------------------------
# Quantidade de fotos
# --------------------------------------------------------------------------


async def test_duas_fotos_e_pouco(client: AsyncClient, cenario: dict):
    response = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(2),
        data=_consentimento(),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == traduzir(Msg.FOTOS_DE_MENOS, minimum=3, quantity=2)


async def test_seis_fotos_e_demais(client: AsyncClient, cenario: dict):
    response = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(6),
        data=_consentimento(),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == traduzir(Msg.FOTOS_DE_MAIS, maximum=5, quantity=6)


# --------------------------------------------------------------------------
# Coerencia entre as fotos
# --------------------------------------------------------------------------


async def test_foto_de_outra_pessoa_no_meio_derruba_o_cadastro(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """O caso que este teste protege: arquivo trocado no painel.

    Sem esta checagem, a base passaria a aceitar duas pessoas como uma so, e
    silenciosamente — nada no fluxo denunciaria o erro.
    """
    arquivos = _fotos_da_mesma_pessoa(2)
    arquivos.append(("images", ("intruso.png", stub_image(PESSOA_B), "image/png")))

    response = await client.post(
        cenario["url"], headers=cenario["headers"], files=arquivos, data=_consentimento()
    )

    assert response.status_code == 422
    assert "same person" in response.json()["detail"]

    # Nada foi gravado.
    assert (await db.execute(select(FaceTemplate))).scalars().all() == []


async def test_foto_sem_rosto_e_recusada_sem_derrubar_as_outras(client: AsyncClient, cenario: dict):
    """Uma foto ruim nao invalida o envio — o RH so reenvia aquela."""
    arquivos = _fotos_da_mesma_pessoa(3)
    arquivos.append(("images", ("vazia.png", stub_image((0, 0, 0)), "image/png")))

    response = await client.post(
        cenario["url"], headers=cenario["headers"], files=arquivos, data=_consentimento()
    )

    assert response.status_code == 201
    corpo = response.json()
    assert len(corpo["created"]) == 3
    assert len(corpo["rejected"]) == 1
    assert corpo["rejected"][0]["filename"] == "vazia.png"


async def test_foto_com_duas_pessoas_e_recusada(client: AsyncClient, cenario: dict):
    arquivos = _fotos_da_mesma_pessoa(3)
    arquivos.append(
        (
            "images",
            ("dupla.png", stub_image_with_faces([PESSOA_A, PESSOA_B]), "image/png"),
        )
    )

    response = await client.post(
        cenario["url"], headers=cenario["headers"], files=arquivos, data=_consentimento()
    )

    recusadas = response.json()["rejected"]
    assert len(recusadas) == 1
    assert recusadas[0]["reason"] == Msg.VARIOS_ROSTOS.value


async def test_fotos_ruins_demais_reprovam_o_cadastro_inteiro(client: AsyncClient, cenario: dict):
    """Se sobrarem menos que o minimo apos a triagem, o cadastro nao se sustenta."""
    arquivos = [
        ("images", ("boa.png", stub_image(PESSOA_A), "image/png")),
        ("images", ("vazia1.png", stub_image((0, 0, 0)), "image/png")),
        ("images", ("vazia2.png", stub_image((0, 0, 0)), "image/png")),
    ]

    response = await client.post(
        cenario["url"], headers=cenario["headers"], files=arquivos, data=_consentimento()
    )

    assert response.status_code == 422
    assert "usable" in response.json()["detail"]


# --------------------------------------------------------------------------
# Consentimento (LGPD)
# --------------------------------------------------------------------------


async def test_sem_consentimento_nao_ha_cadastro(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Sem base legal nao ha tratamento de dado biometrico."""
    response = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(granted=False),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == traduzir(Msg.CONSENTIMENTO_OBRIGATORIO)
    assert (await db.execute(select(FaceTemplate))).scalars().all() == []


async def test_consentimento_e_registrado_com_versao_do_termo(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Sem a versao nao da para provar *o que* a pessoa aceitou."""
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    consentimento = await db.scalar(select(Consent))

    assert consentimento is not None
    assert consentimento.consent_type is ConsentType.BIOMETRIC
    assert consentimento.policy_version == VERSAO_DO_TERMO
    assert consentimento.granted_at is not None
    assert consentimento.revoked_at is None
    assert consentimento.employee_id == cenario["funcionario"].id


# --------------------------------------------------------------------------
# Substituicao e desativacao
# --------------------------------------------------------------------------


async def test_recadastro_desativa_os_templates_anteriores(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    segundo = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    assert segundo.json()["deactivated_previous"] == 3

    todos = (await db.execute(select(FaceTemplate))).scalars().all()
    ativos = [t for t in todos if t.is_active]
    inativos = [t for t in todos if not t.is_active]

    # Os antigos continuam existindo: o historico de pontos aponta para eles.
    assert len(todos) == 6
    assert len(ativos) == 3
    assert len(inativos) == 3
    assert all(t.deactivated_at is not None for t in inativos)


async def test_listagem_traz_apenas_os_ativos_por_padrao(client: AsyncClient, cenario: dict):
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    ativos = await client.get(cenario["url"], headers=cenario["headers"])
    completo = await client.get(
        f"{cenario['url']}?include_inactive=true", headers=cenario["headers"]
    )

    assert ativos.json()["total"] == 3
    assert completo.json()["total"] == 6


async def test_desativar_um_template(client: AsyncClient, db: AsyncSession, cenario: dict):
    criado = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )
    template_id = criado.json()["created"][0]["id"]

    response = await client.delete(f"{cenario['url']}/{template_id}", headers=cenario["headers"])

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Exclusao logica: o registro permanece.
    ainda_existe = await db.scalar(select(FaceTemplate).where(FaceTemplate.id == template_id))
    assert ainda_existe is not None


# --------------------------------------------------------------------------
# Dado sensivel nunca sai pela API
# --------------------------------------------------------------------------


async def test_nenhuma_resposta_carrega_o_embedding(client: AsyncClient, cenario: dict):
    criado = await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )
    listagem = await client.get(cenario["url"], headers=cenario["headers"])
    ficha = await client.get(
        f"/api/v1/employees/{cenario['funcionario'].id}", headers=cenario["headers"]
    )

    for resposta in (criado, listagem, ficha):
        corpo = resposta.text.lower()
        assert "embedding" not in corpo
        assert "source_image_key" not in corpo
        assert "password" not in corpo


# --------------------------------------------------------------------------
# Imagem em repouso
# --------------------------------------------------------------------------


async def test_imagem_e_gravada_cifrada(
    client: AsyncClient, db: AsyncSession, cenario: dict, storage, storage_dir
):
    """Os bytes em disco nao podem ser a imagem original.

    Foto de rosto e dado biometrico: gravar em claro nao e aceitavel nem em
    disco local de desenvolvimento.
    """
    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    template = await db.scalar(select(FaceTemplate))
    assert template is not None

    # Lido sem passar pela camada de criptografia: e o que um invasor com
    # acesso ao disco enxergaria.
    bruto = await LocalStorage(storage_dir).load(template.source_image_key)

    assert not bruto.startswith(b"\x89PNG"), "A assinatura de PNG vazou em claro"
    assert stub_image(PESSOA_A) not in bruto

    # Mas a aplicacao continua lendo a imagem intacta.
    recuperada = await storage.load(template.source_image_key)
    imagens_enviadas = {
        stub_image(PESSOA_A),
        *(stub_image_variant(PESSOA_A, shift=i * 4) for i in range(1, 3)),
    }
    assert recuperada in imagens_enviadas


async def test_imagem_adulterada_no_disco_nao_e_aceita(
    client: AsyncClient, db: AsyncSession, cenario: dict, storage, storage_dir
):
    """AES-GCM autentica: conteudo alterado falha na leitura em vez de virar lixo."""
    from app.services.storage import DecryptionError

    await client.post(
        cenario["url"],
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )
    template = await db.scalar(select(FaceTemplate))

    caminho = storage_dir / template.source_image_key
    adulterado = bytearray(caminho.read_bytes())
    adulterado[-1] ^= 0xFF
    caminho.write_bytes(bytes(adulterado))

    with pytest.raises(DecryptionError):
        await storage.load(template.source_image_key)


# --------------------------------------------------------------------------
# Isolamento entre empresas
# --------------------------------------------------------------------------


async def test_nao_cadastra_biometria_de_funcionario_de_outra_empresa(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    outra = await create_tenant(db, slug="vizinha")
    alheio = await create_employee(db, outra, external_code="X1")
    await db.commit()

    response = await client.post(
        f"/api/v1/employees/{alheio.id}/face-templates",
        headers=cenario["headers"],
        files=_fotos_da_mesma_pessoa(3),
        data=_consentimento(),
    )

    assert response.status_code == 404
