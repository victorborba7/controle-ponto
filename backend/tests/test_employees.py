"""Cadastro de funcionarios pelo painel."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Employee
from app.models.enums import EmployeeStatus, UserRole
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    create_admin,
    create_employee,
    create_site,
    create_tenant,
    device_payload,
    login_admin,
)


@pytest.fixture
async def empresa(db: AsyncSession):
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com", role=UserRole.OWNER)
    site = await create_site(db, tenant)
    await db.commit()
    return {"tenant": tenant, "site": site}


@pytest.fixture
async def sessao(client: AsyncClient, empresa: dict) -> dict[str, str]:
    login = await login_admin(client, empresa["tenant"], "rh@acme.com")
    return auth_header(login["tokens"])


# --------------------------------------------------------------------------
# Cadastro
# --------------------------------------------------------------------------


async def test_cadastrar_funcionario(client: AsyncClient, sessao: dict):
    response = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={
            "external_code": "0007",
            "name": "Joao da Silva",
            "cpf": "123.456.789-00",
            "job_title": "Mecanico",
        },
    )

    assert response.status_code == 201, response.text
    corpo = response.json()
    assert corpo["external_code"] == "0007"
    assert corpo["status"] == "active"
    assert corpo["has_app_credentials"] is False
    assert corpo["active_face_templates"] == 0


async def test_cpf_e_normalizado(client: AsyncClient, sessao: dict):
    """Duas grafias do mesmo CPF furariam a unicidade se nao normalizasse."""
    response = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={"external_code": "0008", "name": "Ana Souza", "cpf": "98765432100"},
    )

    assert response.json()["cpf"] == "987.654.321-00"


async def test_cpf_invalido_e_recusado(client: AsyncClient, sessao: dict):
    response = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={"external_code": "0009", "name": "Ze", "cpf": "123"},
    )
    assert response.status_code == 422


async def test_matricula_duplicada_na_mesma_empresa(client: AsyncClient, sessao: dict):
    dados = {"external_code": "0010", "name": "Primeiro"}
    await client.post("/api/v1/employees", headers=sessao, json=dados)

    repetido = await client.post(
        "/api/v1/employees", headers=sessao, json={**dados, "name": "Segundo"}
    )

    assert repetido.status_code == 409
    assert "matricula" in repetido.json()["detail"].lower()


async def test_cpf_duplicado_na_mesma_empresa(client: AsyncClient, sessao: dict):
    await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={"external_code": "0011", "name": "Um", "cpf": "111.222.333-44"},
    )
    repetido = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={"external_code": "0012", "name": "Outro", "cpf": "11122233344"},
    )

    assert repetido.status_code == 409


async def test_mesma_matricula_em_empresas_diferentes_e_permitida(
    client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict
):
    """Matricula e unica por empresa, nao globalmente."""
    outra = await create_tenant(db, slug="outra")
    await create_admin(db, outra, email="rh@outra.com")
    await db.commit()

    await client.post(
        "/api/v1/employees", headers=sessao, json={"external_code": "0013", "name": "Da Acme"}
    )

    login_outra = await login_admin(client, outra, "rh@outra.com")
    na_outra = await client.post(
        "/api/v1/employees",
        headers=auth_header(login_outra["tokens"]),
        json={"external_code": "0013", "name": "Da Outra"},
    )

    assert na_outra.status_code == 201


async def test_senha_inicial_habilita_o_login_no_app(client: AsyncClient, sessao: dict):
    criado = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={
            "external_code": "0014",
            "name": "Com Senha",
            "initial_password": "primeiro-acesso",
        },
    )
    assert criado.json()["has_app_credentials"] is True

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0014",
            "password": "primeiro-acesso",
            "device": device_payload(),
        },
    )
    assert login.status_code == 200
    # Senha definida pelo RH e provisoria.
    assert login.json()["employee"]["must_change_password"] is True


async def test_site_de_outra_empresa_e_recusado(
    client: AsyncClient, db: AsyncSession, sessao: dict
):
    """A FK do banco nao sabe nada sobre tenants; a checagem e nossa."""
    outra = await create_tenant(db, slug="empresa-vizinha")
    site_alheio = await create_site(db, outra, name="Hangar da vizinha")
    await db.commit()

    response = await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={
            "external_code": "0015",
            "name": "Tentativa",
            "default_site_id": str(site_alheio.id),
        },
    )

    assert response.status_code == 422
    assert "nao encontrado" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# Consulta e atualizacao
# --------------------------------------------------------------------------


async def test_listagem_filtra_por_status(
    client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict
):
    await create_employee(db, empresa["tenant"], external_code="A1", name="Ativo")
    await create_employee(
        db,
        empresa["tenant"],
        external_code="A2",
        name="Desligado",
        status=EmployeeStatus.INACTIVE,
    )
    await db.commit()

    ativos = await client.get("/api/v1/employees?status=active", headers=sessao)
    nomes = {item["name"] for item in ativos.json()["items"]}

    assert nomes == {"Ativo"}


async def test_atualizacao_parcial_preserva_o_resto(
    client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict
):
    funcionario = await create_employee(
        db, empresa["tenant"], external_code="B1", name="Nome Antigo", job_title="Mecanico"
    )
    await db.commit()

    response = await client.patch(
        f"/api/v1/employees/{funcionario.id}", headers=sessao, json={"name": "Nome Novo"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome Novo"
    assert response.json()["job_title"] == "Mecanico"


async def test_desativar_nao_apaga(
    client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict
):
    """Delete real levaria junto o historico de pontos."""
    funcionario = await create_employee(db, empresa["tenant"], external_code="C1")
    await db.commit()

    response = await client.post(f"/api/v1/employees/{funcionario.id}/deactivate", headers=sessao)

    assert response.json()["status"] == "inactive"
    assert await db.scalar(select(Employee).where(Employee.id == funcionario.id)) is not None


async def test_funcionario_desativado_perde_o_acesso(
    client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict
):
    funcionario = await create_employee(
        db, empresa["tenant"], external_code="C2", password=TEST_PASSWORD
    )
    await db.commit()

    await client.post(f"/api/v1/employees/{funcionario.id}/deactivate", headers=sessao)

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "C2",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    assert login.status_code == 401


async def test_redefinir_senha(client: AsyncClient, db: AsyncSession, sessao: dict, empresa: dict):
    funcionario = await create_employee(db, empresa["tenant"], external_code="D1")
    await db.commit()

    reset = await client.post(
        f"/api/v1/employees/{funcionario.id}/password",
        headers=sessao,
        json={"new_password": "senha-nova-123"},
    )
    assert reset.status_code == 204

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "D1",
            "password": "senha-nova-123",
            "device": device_payload(),
        },
    )
    assert login.status_code == 200


# --------------------------------------------------------------------------
# Permissoes
# --------------------------------------------------------------------------


async def test_perfil_de_leitura_nao_cadastra(client: AsyncClient, db: AsyncSession, empresa: dict):
    await create_admin(db, empresa["tenant"], email="leitor@acme.com", role=UserRole.VIEWER)
    await db.commit()

    login = await login_admin(client, empresa["tenant"], "leitor@acme.com")

    resposta = await client.post(
        "/api/v1/employees",
        headers=auth_header(login["tokens"]),
        json={"external_code": "0099", "name": "Nao Deve Entrar"},
    )
    assert resposta.status_code == 403


async def test_perfil_de_leitura_consulta_normalmente(
    client: AsyncClient, db: AsyncSession, empresa: dict
):
    await create_admin(db, empresa["tenant"], email="leitor2@acme.com", role=UserRole.VIEWER)
    await db.commit()

    login = await login_admin(client, empresa["tenant"], "leitor2@acme.com")
    resposta = await client.get("/api/v1/employees", headers=auth_header(login["tokens"]))

    assert resposta.status_code == 200


async def test_funcionario_nao_acessa_o_cadastro(
    client: AsyncClient, db: AsyncSession, empresa: dict
):
    await create_employee(db, empresa["tenant"], external_code="E1")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "E1",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )

    resposta = await client.get("/api/v1/employees", headers=auth_header(login.json()["tokens"]))
    assert resposta.status_code == 403


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------


async def test_cadastro_gera_registro_de_auditoria(
    client: AsyncClient, db: AsyncSession, sessao: dict
):
    await client.post(
        "/api/v1/employees",
        headers=sessao,
        json={"external_code": "F1", "name": "Auditado"},
    )

    registros = (await db.execute(select(AuditLog))).scalars().all()
    criacoes = [r for r in registros if r.entity_type == "employee"]

    assert len(criacoes) == 1
    assert criacoes[0].payload["external_code"] == "F1"
    assert criacoes[0].actor_type == "user"


async def test_auditoria_nao_registra_operacao_revertida(
    client: AsyncClient, db: AsyncSession, sessao: dict
):
    """Auditoria participa da mesma transacao: 409 nao deixa rastro falso."""
    dados = {"external_code": "G1", "name": "Primeiro"}
    await client.post("/api/v1/employees", headers=sessao, json=dados)

    antes = len((await db.execute(select(AuditLog))).scalars().all())
    await client.post("/api/v1/employees", headers=sessao, json=dados)  # 409
    depois = len((await db.execute(select(AuditLog))).scalars().all())

    assert depois == antes
