"""Autenticacao: login, escopos, rotacao e revogacao de sessao."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, RefreshToken
from app.models.enums import EmployeeStatus
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    create_admin,
    create_employee,
    create_tenant,
    device_payload,
    login_admin,
)


@pytest.fixture
async def tenant_com_pessoal(db: AsyncSession):
    tenant = await create_tenant(db, slug="acme")
    admin = await create_admin(db, tenant, email="rh@acme.com")
    employee = await create_employee(db, tenant, external_code="0001", name="Joao")
    await db.commit()
    return {"tenant": tenant, "admin": admin, "employee": employee}


# --------------------------------------------------------------------------
# Login do painel
# --------------------------------------------------------------------------


async def test_login_admin_devolve_par_de_tokens(client: AsyncClient, tenant_com_pessoal: dict):
    body = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")

    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] > 0
    assert body["user"]["email"] == "rh@acme.com"
    assert body["tenant"]["slug"] == "acme"


async def test_login_admin_com_senha_errada(client: AsyncClient, tenant_com_pessoal: dict):
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "rh@acme.com", "password": "errada"},
    )
    assert response.status_code == 401


async def test_login_admin_desativado(client: AsyncClient, db: AsyncSession):
    tenant = await create_tenant(db, slug="inativos")
    await create_admin(db, tenant, email="ex@inativos.com", is_active=False)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "inativos", "email": "ex@inativos.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401


async def test_login_com_tenant_inexistente(client: AsyncClient, tenant_com_pessoal: dict):
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "nao-existe", "email": "rh@acme.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401


async def test_mensagem_de_erro_nao_distingue_usuario_de_senha(
    client: AsyncClient, tenant_com_pessoal: dict
):
    """As duas falhas respondem igual, para nao permitir enumerar contas."""
    inexistente = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "ninguem@acme.com", "password": TEST_PASSWORD},
    )
    senha_errada = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "rh@acme.com", "password": "errada"},
    )

    assert inexistente.status_code == senha_errada.status_code == 401
    assert inexistente.json()["detail"] == senha_errada.json()["detail"]


# --------------------------------------------------------------------------
# Login do app e pareamento do aparelho
# --------------------------------------------------------------------------


async def test_login_funcionario_registra_o_aparelho(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    payload = device_payload("aparelho-do-joao")
    response = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": payload,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["employee"]["external_code"] == "0001"
    assert body["device_id"]

    device = await db.scalar(
        select(Device).where(Device.device_fingerprint == "aparelho-do-joao")
    )
    assert device is not None
    assert device.employee_id == tenant_com_pessoal["employee"].id
    assert device.model == "Pixel 7"


async def test_segundo_login_reaproveita_o_mesmo_aparelho(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    payload = device_payload("aparelho-fixo")
    credenciais = {
        "tenant_slug": "acme",
        "external_code": "0001",
        "password": TEST_PASSWORD,
        "device": payload,
    }

    primeiro = await client.post("/api/v1/auth/employee/login", json=credenciais)
    segundo = await client.post("/api/v1/auth/employee/login", json=credenciais)

    assert primeiro.json()["device_id"] == segundo.json()["device_id"]

    total = await db.scalar(
        select(Device).where(Device.device_fingerprint == "aparelho-fixo")
    )
    assert total is not None


async def test_funcionario_desligado_nao_loga(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    employee = tenant_com_pessoal["employee"]
    employee.status = EmployeeStatus.INACTIVE
    await db.commit()

    response = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    assert response.status_code == 401


async def test_funcionario_sem_senha_cadastrada_nao_loga(client: AsyncClient, db: AsyncSession):
    """Funcionario cadastrado pelo RH mas ainda sem credencial do app."""
    tenant = await create_tenant(db, slug="sem-senha")
    await create_employee(db, tenant, external_code="0009", password=None)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "sem-senha",
            "external_code": "0009",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------
# Escopos: painel x app
# --------------------------------------------------------------------------


async def test_endpoint_sem_token(client: AsyncClient):
    response = await client.get("/api/v1/employees")
    assert response.status_code == 401


async def test_token_adulterado_e_rejeitado(client: AsyncClient, tenant_com_pessoal: dict):
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")
    adulterado = login["tokens"]["access_token"][:-4] + "AAAA"

    response = await client.get(
        "/api/v1/employees", headers={"Authorization": f"Bearer {adulterado}"}
    )
    assert response.status_code == 401


async def test_token_de_funcionario_nao_abre_o_painel(
    client: AsyncClient, tenant_com_pessoal: dict
):
    """Escopo do app nao da acesso a dados administrativos."""
    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    tokens = login.json()["tokens"]

    response = await client.get("/api/v1/employees", headers=auth_header(tokens))
    assert response.status_code == 403


async def test_refresh_token_nao_serve_como_token_de_acesso(
    client: AsyncClient, tenant_com_pessoal: dict
):
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")
    refresh = login["tokens"]["refresh_token"]

    response = await client.get(
        "/api/v1/employees", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


async def test_me_descreve_a_sessao(client: AsyncClient, tenant_com_pessoal: dict):
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")

    response = await client.get("/api/v1/auth/me", headers=auth_header(login["tokens"]))

    assert response.status_code == 200
    body = response.json()
    assert body["subject_type"] == "user"
    assert body["role"] == "owner"
    assert body["tenant_id"] == str(tenant_com_pessoal["tenant"].id)
    assert body["name"] == "Admin de Teste"


# --------------------------------------------------------------------------
# Rotacao e revogacao
# --------------------------------------------------------------------------


async def test_refresh_devolve_par_novo(client: AsyncClient, tenant_com_pessoal: dict):
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["tokens"]["refresh_token"]},
    )

    assert response.status_code == 200
    novo = response.json()
    assert novo["refresh_token"] != login["tokens"]["refresh_token"]

    # O token novo abre a API.
    protegido = await client.get("/api/v1/employees", headers=auth_header(novo))
    assert protegido.status_code == 200


async def test_refresh_usado_duas_vezes_derruba_a_sessao(
    client: AsyncClient, tenant_com_pessoal: dict
):
    """Reapresentar um refresh ja gasto revoga tudo do titular.

    Um token gasto reaparecendo significa que existem duas copias dele em
    circulacao, e nao ha como saber qual e a legitima. Derrubar as sessoes e
    a resposta segura.
    """
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")
    original = login["tokens"]["refresh_token"]

    primeiro = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert primeiro.status_code == 200
    sucessor = primeiro.json()["refresh_token"]

    # Reuso do token antigo: rejeitado...
    reuso = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert reuso.status_code == 401

    # ...e o sucessor legitimo tambem cai, porque a sessao inteira foi revogada.
    apos_alerta = await client.post("/api/v1/auth/refresh", json={"refresh_token": sucessor})
    assert apos_alerta.status_code == 401


async def test_rotacao_encadeia_o_sucessor(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    """A cadeia de rotacao fica registrada, para investigar roubo de token."""
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")
    await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["tokens"]["refresh_token"]}
    )

    resultado = await db.execute(select(RefreshToken).order_by(RefreshToken.created_at))
    tokens = resultado.scalars().all()

    assert len(tokens) == 2
    antigo, novo = tokens
    assert antigo.revoked_at is not None
    assert antigo.replaced_by_id == novo.id
    assert novo.revoked_at is None


async def test_logout_revoga_o_refresh(client: AsyncClient, tenant_com_pessoal: dict):
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")
    refresh = login["tokens"]["refresh_token"]

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert logout.status_code == 204

    depois = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert depois.status_code == 401


async def test_logout_com_token_desconhecido_e_silencioso(client: AsyncClient):
    """Nao confirma se o token existia — nada a revelar a quem chamou."""
    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": "token-que-nunca-existiu"}
    )
    assert response.status_code == 204


async def test_refresh_de_usuario_desativado_falha(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    """Desativar alguem passa a valer no proximo refresh, sem esperar a sessao expirar."""
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")

    tenant_com_pessoal["admin"].is_active = False
    await db.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["tokens"]["refresh_token"]},
    )
    assert response.status_code == 401


async def test_refresh_do_funcionario_preserva_o_aparelho(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    """O vinculo com o device sobrevive a rotacao — senao o ponto perderia a origem."""
    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload("aparelho-persistente"),
        },
    )
    device_id = login.json()["device_id"]

    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["tokens"]["refresh_token"]},
    )
    assert refreshed.status_code == 200

    me = await client.get("/api/v1/auth/me", headers=auth_header(refreshed.json()))
    assert me.json()["device_id"] == device_id


async def test_funcionario_de_outro_tenant_nao_reaproveita_matricula(
    client: AsyncClient, db: AsyncSession, tenant_com_pessoal: dict
):
    """Matricula 0001 existe nas duas empresas e cada uma so abre a sua."""
    outra = await create_tenant(db, slug="outra-empresa")
    await create_employee(db, outra, external_code="0001", name="Outro Joao")
    await db.commit()

    response = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "outra-empresa",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["employee"]["name"] == "Outro Joao"
    assert body["tenant"]["slug"] == "outra-empresa"


async def test_embedding_nunca_aparece_na_api(client: AsyncClient, tenant_com_pessoal: dict):
    """Nenhuma resposta pode carregar dado biometrico."""
    login = await login_admin(client, tenant_com_pessoal["tenant"], "rh@acme.com")

    listagem = await client.get("/api/v1/employees", headers=auth_header(login["tokens"]))
    corpo = listagem.text.lower()

    assert "embedding" not in corpo
    assert "password" not in corpo
    assert "cpf" not in corpo


async def test_funcionario_existe_mas_o_teste_confirma_o_repo(db: AsyncSession):
    """Sanidade da fabrica de dados usada pelos demais testes."""
    tenant = await create_tenant(db, slug="sanidade")
    employee = await create_employee(db, tenant, external_code="9999")
    await db.commit()

    encontrado = await db.scalar(select(Employee).where(Employee.id == employee.id))
    assert encontrado is not None
    assert encontrado.tenant_id == tenant.id
