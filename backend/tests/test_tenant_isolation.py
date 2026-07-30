"""Isolamento entre empresas.

Este e o teste que sustenta a promessa central da arquitetura: os dados de uma
empresa nao alcancam outra. Ele existe desde antes de haver o segundo cliente
justamente porque o custo de descobrir um vazamento em producao e alto demais
para depender de revisao manual de cada consulta.

Cenario: dois tenants (A e B), cada um com seu admin e seus funcionarios.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantRepository
from app.models import Employee
from tests.conftest import (
    auth_header,
    create_admin,
    create_employee,
    create_tenant,
    login_admin,
)

# Mesmo event loop das fixtures de sessao (ver pyproject.toml).
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
async def two_tenants(db: AsyncSession):
    """Duas empresas com dados proprios, prontas para o confronto."""
    tenant_a = await create_tenant(db, slug="empresa-a", name="Empresa A")
    tenant_b = await create_tenant(db, slug="empresa-b", name="Empresa B")

    admin_a = await create_admin(db, tenant_a, email="admin@empresa-a.com")
    admin_b = await create_admin(db, tenant_b, email="admin@empresa-b.com")

    employee_a = await create_employee(db, tenant_a, external_code="A001", name="Joao da A")
    employee_b = await create_employee(db, tenant_b, external_code="B001", name="Ana da B")

    await db.commit()
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "employee_a": employee_a,
        "employee_b": employee_b,
    }


async def test_listagem_so_traz_funcionarios_do_proprio_tenant(
    client: AsyncClient, two_tenants: dict
):
    login = await login_admin(client, two_tenants["tenant_a"], "admin@empresa-a.com")

    response = await client.get("/api/v1/employees", headers=auth_header(login["tokens"]))

    assert response.status_code == 200
    body = response.json()
    codigos = {item["external_code"] for item in body["items"]}
    assert codigos == {"A001"}
    assert body["total"] == 1


async def test_buscar_funcionario_de_outro_tenant_responde_404(
    client: AsyncClient, two_tenants: dict
):
    """404, e nao 403: responder 'proibido' ja confirmaria que o id existe."""
    login = await login_admin(client, two_tenants["tenant_a"], "admin@empresa-a.com")
    id_do_outro_tenant = two_tenants["employee_b"].id

    response = await client.get(
        f"/api/v1/employees/{id_do_outro_tenant}",
        headers=auth_header(login["tokens"]),
    )

    assert response.status_code == 404


async def test_cada_admin_enxerga_apenas_a_propria_empresa(
    client: AsyncClient, two_tenants: dict
):
    """O mesmo endpoint responde coisas diferentes conforme o token."""
    login_a = await login_admin(client, two_tenants["tenant_a"], "admin@empresa-a.com")
    login_b = await login_admin(client, two_tenants["tenant_b"], "admin@empresa-b.com")

    resposta_a = await client.get("/api/v1/employees", headers=auth_header(login_a["tokens"]))
    resposta_b = await client.get("/api/v1/employees", headers=auth_header(login_b["tokens"]))

    nomes_a = {item["name"] for item in resposta_a.json()["items"]}
    nomes_b = {item["name"] for item in resposta_b.json()["items"]}

    assert nomes_a == {"Joao da A"}
    assert nomes_b == {"Ana da B"}
    assert nomes_a.isdisjoint(nomes_b)


async def test_admin_nao_loga_no_tenant_errado(client: AsyncClient, two_tenants: dict):
    """A credencial da empresa A nao vale informando o slug da empresa B.

    Email e unico por tenant, entao sem esta checagem um admin poderia entrar
    em qualquer empresa que tivesse um homonimo cadastrado.
    """
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={
            "tenant_slug": two_tenants["tenant_b"].slug,
            "email": "admin@empresa-a.com",
            "password": "senha-de-teste",
        },
    )

    assert response.status_code == 401


# --------------------------------------------------------------------------
# O repositorio, testado direto — a camada onde o isolamento e imposto
# --------------------------------------------------------------------------


async def test_repositorio_nao_devolve_registro_de_outro_tenant(
    db: AsyncSession, two_tenants: dict
):
    repo = TenantRepository(db, two_tenants["tenant_a"].id)

    proprio = await repo.get(Employee, two_tenants["employee_a"].id)
    alheio = await repo.get(Employee, two_tenants["employee_b"].id)

    assert proprio is not None
    assert alheio is None


async def test_repositorio_ignora_tenant_id_vindo_do_payload(
    db: AsyncSession, two_tenants: dict
):
    """Tentar plantar um registro em outra empresa nao funciona.

    Um payload malicioso (ou um bug de mapeamento) que preencha tenant_id e
    sobrescrito pelo tenant do repositorio.
    """
    repo = TenantRepository(db, two_tenants["tenant_a"].id)

    intruso = Employee(
        tenant_id=two_tenants["tenant_b"].id,  # tentativa de gravar na empresa B
        external_code="X999",
        name="Registro Plantado",
    )
    repo.add(intruso)
    await db.flush()

    assert intruso.tenant_id == two_tenants["tenant_a"].id

    repo_b = TenantRepository(db, two_tenants["tenant_b"].id)
    assert await repo_b.get(Employee, intruso.id) is None


async def test_contagem_respeita_o_tenant(db: AsyncSession, two_tenants: dict):
    await create_employee(db, two_tenants["tenant_a"], external_code="A002", name="Outro da A")
    await db.commit()

    repo_a = TenantRepository(db, two_tenants["tenant_a"].id)
    repo_b = TenantRepository(db, two_tenants["tenant_b"].id)

    assert await repo_a.count(Employee) == 2
    assert await repo_b.count(Employee) == 1


async def test_tenant_inexistente_nao_enxerga_nada(db: AsyncSession, two_tenants: dict):
    """Um tenant_id qualquer nao serve de chave-mestra."""
    repo = TenantRepository(db, uuid.uuid4())

    assert await repo.count(Employee) == 0
    assert await repo.list(Employee) == []
    assert await repo.get(Employee, two_tenants["employee_a"].id) is None
