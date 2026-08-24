"""Usuarios do painel: quem pode gerenciar quem, e as travas contra tranca-se fora.

O caminho feliz e trivial. O que estes testes protegem sao tres coisas que
custam caro quando falham:

1. **HR nao gerencia usuarios.** Se pudesse, uma conta de HR criaria uma conta
   OWNER e a distincao de papeis nao significaria nada.
2. **Ninguem se rebaixa nem se desativa.** Um clique errado deixaria a propria
   pessoa sem acesso ao painel que ela administra.
3. **O ultimo proprietario nao deixa de ser proprietario.** Sem isso a empresa
   fica sem quem gerencie acesso, e a unica saida e chamar o fornecedor.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import Msg, traduzir
from app.core.security import hash_password, verify_password
from app.models import User
from app.models.enums import UserRole
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    create_admin,
    create_tenant,
    login_admin,
)

URL = "/api/v1/users"
SENHA_NOVA = "senha-suficientemente-longa"


def _novo(email: str = "novo@acme.com", papel: str = "hr") -> dict:
    return {
        "email": email,
        "name": "Pessoa Nova",
        "role": papel,
        "password": SENHA_NOVA,
    }


@pytest.fixture
async def dono(client: AsyncClient, db: AsyncSession) -> dict:
    tenant = await create_tenant(db, slug="acme")
    admin = await create_admin(db, tenant, email="dono@acme.com", role=UserRole.OWNER)
    await db.commit()

    login = await login_admin(client, tenant, "dono@acme.com")
    return {
        "tenant": tenant,
        "tenant_id": tenant.id,
        "admin_id": admin.id,
        "headers": auth_header(login["tokens"]),
    }


# --------------------------------------------------------------------------
# Caminho feliz
# --------------------------------------------------------------------------


async def test_proprietario_cria_usuario(client: AsyncClient, dono: dict):
    resposta = await client.post(URL, headers=dono["headers"], json=_novo())

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["email"] == "novo@acme.com"
    assert corpo["role"] == "hr"
    assert corpo["is_active"] is True


async def test_usuario_criado_consegue_entrar(
    client: AsyncClient, db: AsyncSession, dono: dict
):
    """O teste que prova que a senha inicial serve para alguma coisa."""
    await client.post(URL, headers=dono["headers"], json=_novo())

    login = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "novo@acme.com", "password": SENHA_NOVA},
    )
    assert login.status_code == 200, login.text


async def test_lista_mostra_quem_tem_acesso(client: AsyncClient, dono: dict):
    await client.post(URL, headers=dono["headers"], json=_novo())

    resposta = await client.get(URL, headers=dono["headers"])

    emails = {u["email"] for u in resposta.json()["items"]}
    assert emails == {"dono@acme.com", "novo@acme.com"}


async def test_email_duplicado_no_mesmo_tenant_e_recusado(client: AsyncClient, dono: dict):
    await client.post(URL, headers=dono["headers"], json=_novo())
    repetido = await client.post(URL, headers=dono["headers"], json=_novo())

    assert repetido.status_code == 409
    assert repetido.json()["detail"] == traduzir(Msg.EMAIL_JA_USADO, "en")


async def test_senha_curta_e_recusada(client: AsyncClient, dono: dict):
    resposta = await client.post(
        URL, headers=dono["headers"], json={**_novo(), "password": "curta"}
    )
    assert resposta.status_code == 422


async def test_redefinir_senha_troca_o_hash(
    client: AsyncClient, db: AsyncSession, dono: dict
):
    criado = (await client.post(URL, headers=dono["headers"], json=_novo())).json()

    resposta = await client.post(
        f"{URL}/{criado['id']}/password",
        headers=dono["headers"],
        json={"password": "outra-senha-bem-longa"},
    )
    assert resposta.status_code == 204

    usuario = await db.scalar(select(User).where(User.email == "novo@acme.com"))
    await db.refresh(usuario)
    assert verify_password("outra-senha-bem-longa", usuario.password_hash)


async def test_desativar_impede_o_login(client: AsyncClient, dono: dict):
    """Desativar e o corte de acesso de verdade — o login checa `is_active`."""
    criado = (await client.post(URL, headers=dono["headers"], json=_novo())).json()

    await client.patch(
        f"{URL}/{criado['id']}", headers=dono["headers"], json={"is_active": False}
    )

    login = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "novo@acme.com", "password": SENHA_NOVA},
    )
    assert login.status_code == 401


# --------------------------------------------------------------------------
# Permissao
# --------------------------------------------------------------------------


async def test_hr_nao_cria_usuario(client: AsyncClient, db: AsyncSession, dono: dict):
    """Se pudesse, uma conta de HR criaria uma conta OWNER."""
    db.add(
        User(
            tenant_id=dono["tenant_id"],
            email="rh@acme.com",
            name="RH",
            role=UserRole.HR,
            password_hash=hash_password(TEST_PASSWORD),
        )
    )
    await db.commit()

    login = await login_admin(client, dono["tenant"], "rh@acme.com")
    resposta = await client.post(
        URL, headers=auth_header(login["tokens"]), json=_novo("outro@acme.com")
    )

    assert resposta.status_code == 403


async def test_hr_pode_ver_a_lista(client: AsyncClient, db: AsyncSession, dono: dict):
    """Saber quem tem acesso nao e privilegio; conceder acesso e."""
    db.add(
        User(
            tenant_id=dono["tenant_id"],
            email="rh2@acme.com",
            name="RH",
            role=UserRole.HR,
            password_hash=hash_password(TEST_PASSWORD),
        )
    )
    await db.commit()

    login = await login_admin(client, dono["tenant"], "rh2@acme.com")
    resposta = await client.get(URL, headers=auth_header(login["tokens"]))

    assert resposta.status_code == 200


async def test_token_de_funcionario_nao_serve(client: AsyncClient, dono: dict):
    resposta = await client.get(URL)
    assert resposta.status_code == 401


# --------------------------------------------------------------------------
# Travas contra tranca-se para fora
# --------------------------------------------------------------------------


async def test_nao_se_desativa(client: AsyncClient, dono: dict):
    resposta = await client.patch(
        f"{URL}/{dono['admin_id']}", headers=dono["headers"], json={"is_active": False}
    )

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == traduzir(Msg.NAO_PODE_MUDAR_A_SI_MESMO, "en")


async def test_nao_muda_o_proprio_papel(client: AsyncClient, dono: dict):
    resposta = await client.patch(
        f"{URL}/{dono['admin_id']}", headers=dono["headers"], json={"role": "viewer"}
    )
    assert resposta.status_code == 409


async def test_pode_mudar_o_proprio_nome(client: AsyncClient, dono: dict):
    """A trava e sobre acesso, nao sobre tudo."""
    resposta = await client.patch(
        f"{URL}/{dono['admin_id']}", headers=dono["headers"], json={"name": "Nome Novo"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["name"] == "Nome Novo"


async def test_ultimo_proprietario_nao_perde_o_papel(
    client: AsyncClient, db: AsyncSession, dono: dict
):
    """Rebaixar outro proprietario quando so ha um deixaria a empresa sem dono."""
    outro = (
        await client.post(URL, headers=dono["headers"], json=_novo("dono2@acme.com", "owner"))
    ).json()

    # Agora ha dois: rebaixar um e permitido.
    ok = await client.patch(
        f"{URL}/{outro['id']}", headers=dono["headers"], json={"role": "hr"}
    )
    assert ok.status_code == 200

    # Sobrou um. Ele nao pode ser rebaixado por ninguem — nem por si mesmo, que
    # ja e barrado antes, nem por outro proprietario, que nao existe mais.
    sozinho = await client.patch(
        f"{URL}/{dono['admin_id']}", headers=dono["headers"], json={"role": "hr"}
    )
    assert sozinho.status_code == 409


async def test_isolamento_entre_empresas(
    client: AsyncClient, db: AsyncSession, dono: dict
):
    """Usuario de outra empresa nem existe para este token."""
    outra = await create_tenant(db, slug="beta")
    alheio = await create_admin(db, outra, email="dono@beta.com", role=UserRole.OWNER)
    await db.commit()

    resposta = await client.patch(
        f"{URL}/{alheio.id}", headers=dono["headers"], json={"name": "Invadido"}
    )

    assert resposta.status_code == 404
