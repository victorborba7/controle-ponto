"""Teto de tentativas de login.

Duas regras, dois ataques diferentes: insistir numa conta (teto por identidade)
e testar uma senha provavel contra a empresa toda (teto por endereco, que conta
identidades distintas). Uma sozinha nao pega a outra — e por isso os dois
cenarios estao aqui lado a lado.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import LoginAttempt
from tests.conftest import (
    TEST_PASSWORD,
    create_admin,
    create_employee,
    create_tenant,
    device_payload,
)


@pytest.fixture
async def empresa(db: AsyncSession):
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com")
    await create_employee(db, tenant, external_code="0001", name="Joao")
    await db.commit()
    return tenant


async def _entrar(client: AsyncClient, *, matricula: str = "0001", senha: str = "errada"):
    return await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": matricula,
            "password": senha,
            "device": device_payload("celular-do-joao"),
        },
    )


# --------------------------------------------------------------------------
# Teto por identidade
# --------------------------------------------------------------------------


async def test_falhas_seguidas_bloqueiam_a_conta(client: AsyncClient, empresa):
    for _ in range(settings.login_max_failures):
        assert (await _entrar(client)).status_code == 401

    bloqueado = await _entrar(client)

    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["Retry-After"]) > 0


async def test_bloqueio_vale_mesmo_com_a_senha_certa(client: AsyncClient, empresa):
    """O teto e conferido **antes** da senha.

    E o que faz dele um teto de verdade: se a senha correta passasse durante o
    bloqueio, bastaria continuar tentando ate acertar — que e exatamente o
    ataque. Tambem e o que evita gastar um hash Argon2 por tentativa.
    """
    for _ in range(settings.login_max_failures):
        await _entrar(client)

    resposta = await _entrar(client, senha=TEST_PASSWORD)

    assert resposta.status_code == 429


async def test_abaixo_do_teto_a_senha_certa_entra(client: AsyncClient, empresa):
    """Errar a senha algumas vezes e vida normal, nao ataque."""
    for _ in range(settings.login_max_failures - 1):
        await _entrar(client)

    resposta = await _entrar(client, senha=TEST_PASSWORD)

    assert resposta.status_code == 200, resposta.text


async def test_login_bem_sucedido_zera_o_contador(client: AsyncClient, db: AsyncSession, empresa):
    """Quem provou ser o titular nao fica a um erro do bloqueio."""
    for _ in range(settings.login_max_failures - 1):
        await _entrar(client)

    assert (await _entrar(client, senha=TEST_PASSWORD)).status_code == 200

    restantes = (await db.execute(select(LoginAttempt))).scalars().all()
    assert restantes == []

    # E o contador recomeca do zero: outra rodada de falhas nao emenda na
    # anterior.
    for _ in range(settings.login_max_failures - 1):
        assert (await _entrar(client)).status_code == 401


async def test_bloqueio_de_uma_conta_nao_atinge_a_outra(client: AsyncClient, db, empresa):
    """Senao trancar um colega seria uma forma barata de sabotagem."""
    await create_employee(db, empresa, external_code="0002", name="Maria")
    await db.commit()

    for _ in range(settings.login_max_failures + 1):
        await _entrar(client, matricula="0001")

    resposta = await _entrar(client, matricula="0002", senha=TEST_PASSWORD)

    assert resposta.status_code == 200, resposta.text


async def test_painel_e_app_contam_separado(client: AsyncClient, empresa):
    """Mesma empresa, credenciais e tabelas diferentes.

    Somar os dois publicos faria o RH ser trancado pelas tentativas erradas de
    um funcionario, e vice-versa.
    """
    for _ in range(settings.login_max_failures + 1):
        await _entrar(client, matricula="0001")

    resposta = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "rh@acme.com", "password": TEST_PASSWORD},
    )

    assert resposta.status_code == 200, resposta.text


# --------------------------------------------------------------------------
# Teto por endereco (senha provavel testada contra varias contas)
# --------------------------------------------------------------------------


async def test_muitas_identidades_falhando_do_mesmo_endereco_bloqueiam_o_endereco(
    client: AsyncClient, empresa
):
    """O ataque que o teto por identidade nao pega.

    Cada matricula falha **uma vez** — nenhuma chega perto do proprio teto —,
    mas o conjunto denuncia alguem varrendo a empresa com uma senha so.
    """
    for numero in range(settings.login_spray_max_identities):
        await _entrar(client, matricula=f"90{numero:02d}")

    # Uma matricula que nem foi tentada ainda: quem esta barrado e o endereco.
    resposta = await _entrar(client, matricula="0001", senha=TEST_PASSWORD)

    assert resposta.status_code == 429


async def test_poucas_identidades_nao_bloqueiam_o_endereco(client: AsyncClient, empresa):
    """Um escritorio inteiro sai por um IP so.

    Contar tentativas em vez de identidades distintas bloquearia a empresa numa
    segunda-feira de dedo errado; ninguem erra a senha de dez colegas.
    """
    for numero in range(settings.login_spray_max_identities - 1):
        await _entrar(client, matricula=f"90{numero:02d}")

    resposta = await _entrar(client, matricula="0001", senha=TEST_PASSWORD)

    assert resposta.status_code == 200, resposta.text


# --------------------------------------------------------------------------
# O que fica gravado
# --------------------------------------------------------------------------


async def test_falha_sobrevive_ao_401(client: AsyncClient, db: AsyncSession, empresa):
    """A dependencia de sessao desfaz a transacao quando o endpoint levanta.

    Sem o commit explicito antes do 401, o contador nunca sairia do zero e o
    teto existiria no codigo, nao no comportamento.
    """
    await _entrar(client)

    linhas = (await db.execute(select(LoginAttempt))).scalars().all()
    assert len(linhas) == 1
    assert linhas[0].failures == 1


async def test_identificador_nao_e_guardado_em_claro(
    client: AsyncClient, db: AsyncSession, empresa
):
    """A tabela acumularia matriculas e e-mails digitados por qualquer um."""
    await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": "acme", "email": "rh@acme.com", "password": "errada"},
    )

    linha = (await db.execute(select(LoginAttempt))).scalars().one()

    assert "rh@acme.com" not in linha.identity_hash
    assert len(linha.identity_hash) == 64
