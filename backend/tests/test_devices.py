"""Aparelhos pareados: revogar de verdade.

O pareamento e o que impede uma credencial vazada de bater ponto de qualquer
celular. Ate aqui ele tinha um buraco: `revoked_at` existia no modelo, nenhum
endpoint o preenchia, e o login limpava o campo — entao revogar um celular
roubado duraria ate quem estivesse com ele digitar a senha.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.messages import Msg, traduzir
from app.models import Device, RefreshToken
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    bater_ponto,
    create_employee,
    device_payload,
)


async def _entrar(client: AsyncClient) -> dict:
    """Login do funcionario do cenario, no mesmo aparelho."""
    resposta = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload("celular-do-joao"),
        },
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.fixture
async def revogar(client: AsyncClient, cenario: dict):
    """Revoga o aparelho do cenario pelo painel."""

    async def _revogar():
        resposta = await client.post(
            f"/api/v1/employees/{cenario['funcionario'].id}/devices/{cenario['device_id']}/revoke",
            headers=cenario["admin"],
        )
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return _revogar


# --------------------------------------------------------------------------
# O efeito da revogacao
# --------------------------------------------------------------------------


async def test_aparelho_revogado_nao_bate_ponto(client: AsyncClient, cenario: dict, revogar):
    await revogar()

    resposta = await bater_ponto(client, cenario)

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == traduzir(Msg.APARELHO_DESVINCULADO)


async def test_revogar_derruba_as_sessoes_abertas(
    client: AsyncClient, db: AsyncSession, cenario: dict, revogar
):
    """Sem isto, quem esta com o celular navega por ate 30 dias.

    O access token e curto e sem estado, mas o refresh vale um mes: cortar so o
    ponto deixaria o historico do funcionario aberto na mao de quem levou o
    aparelho.
    """
    await revogar()

    tokens = (
        (
            await db.execute(
                select(RefreshToken).where(
                    RefreshToken.device_id == uuid.UUID(cenario["device_id"])
                )
            )
        )
        .scalars()
        .all()
    )

    assert tokens
    assert all(token.revoked_at is not None for token in tokens)


async def test_login_nao_reabilita_aparelho_revogado(
    client: AsyncClient, db: AsyncSession, cenario: dict, revogar
):
    """O defeito que motivou tudo isto.

    Entrar de novo reabilitava o aparelho, o que transformava a revogacao num
    aviso: quem tivesse a senha desfazia a decisao do RH sozinho.
    """
    await revogar()

    novo_login = await _entrar(client)

    aparelho = await db.get(Device, uuid.UUID(cenario["device_id"]))
    assert aparelho is not None
    assert aparelho.revoked_at is not None

    # E o token novo tambem nao bate ponto: quem barra e o aparelho, nao a
    # sessao.
    resposta = await bater_ponto(client, cenario, headers=auth_header(novo_login["tokens"]))
    assert resposta.status_code == 403


async def test_login_continua_valendo_com_aparelho_revogado(
    client: AsyncClient, cenario: dict, revogar
):
    """Entrar segue permitido de proposito.

    Barrar o login tiraria do funcionario o proprio historico sem ganho de
    seguranca — o que precisa parar e o registro de ponto, e ele para.
    """
    await revogar()

    login = await _entrar(client)

    historico = await client.get("/api/v1/time-entries/me", headers=auth_header(login["tokens"]))
    assert historico.status_code == 200


# --------------------------------------------------------------------------
# Reautorizacao
# --------------------------------------------------------------------------


async def test_rh_reautoriza_e_o_ponto_volta(client: AsyncClient, cenario: dict, revogar):
    await revogar()

    reautorizado = await client.post(
        f"/api/v1/employees/{cenario['funcionario'].id}/devices/{cenario['device_id']}/authorize",
        headers=cenario["admin"],
    )

    assert reautorizado.status_code == 200, reautorizado.text
    assert reautorizado.json()["revoked_at"] is None

    resposta = await bater_ponto(client, cenario)
    assert resposta.status_code == 201, resposta.text


async def test_revogar_duas_vezes_mantem_a_data_original(
    client: AsyncClient, cenario: dict, revogar
):
    """A data e o que responde "desde quando esse aparelho esta fora?"."""
    primeira = await revogar()
    segunda = await revogar()

    assert primeira["revoked_at"] == segunda["revoked_at"]


# --------------------------------------------------------------------------
# Consulta e escopo
# --------------------------------------------------------------------------


async def test_painel_lista_os_aparelhos_do_funcionario(client: AsyncClient, cenario: dict):
    resposta = await client.get(
        f"/api/v1/employees/{cenario['funcionario'].id}/devices",
        headers=cenario["admin"],
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["id"] == cenario["device_id"]
    assert corpo["items"][0]["platform"] == "android"
    assert corpo["items"][0]["revoked_at"] is None


async def test_listagem_nao_expoe_a_impressao_digital_do_aparelho(
    client: AsyncClient, cenario: dict
):
    """E o segredo que amarra o celular a pessoa no proximo login."""
    resposta = await client.get(
        f"/api/v1/employees/{cenario['funcionario'].id}/devices",
        headers=cenario["admin"],
    )

    assert "celular-do-joao" not in resposta.text
    assert "fingerprint" not in resposta.text


async def test_aparelho_de_outro_funcionario_nao_e_alcancavel(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """A URL diz de quem e o aparelho; a acao precisa concordar com ela."""
    outro = await create_employee(db, cenario["tenant"], external_code="0002", name="Maria")
    await db.commit()

    resposta = await client.post(
        f"/api/v1/employees/{outro.id}/devices/{cenario['device_id']}/revoke",
        headers=cenario["admin"],
    )

    assert resposta.status_code == 404


async def test_funcionario_nao_revoga_o_proprio_aparelho(client: AsyncClient, cenario: dict):
    """Revogar e ato do RH. Token do app nao abre o painel."""
    resposta = await client.post(
        f"/api/v1/employees/{cenario['funcionario'].id}/devices/{cenario['device_id']}/revoke",
        headers=cenario["app"],
    )

    assert resposta.status_code == 403
