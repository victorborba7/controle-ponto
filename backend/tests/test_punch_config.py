"""Configuracao de batida: o RH monta, o app obedece, o registro congela.

O que estes testes protegem, em uma frase: mudar a configuracao amanha nao
pode reescrever o que foi batido hoje.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    auth_header,
    bater_ponto,
    create_admin,
    create_tenant,
    login_admin,
)

CONFIG = "/api/v1/punch-config"


async def configurar(client: AsyncClient, cenario: dict, **campos):
    """Grava a configuracao da empresa do cenario, como o RH faria."""
    corpo = {
        "note_mode": "hidden",
        "note_prompt": None,
        "label_mode": "hidden",
        "label_required": False,
        "labels": [],
        **campos,
    }
    return await client.put(CONFIG, headers=cenario["admin"], json=corpo)


def rotulo(name: str, entry_type: str, is_active: bool = True) -> dict:
    return {"name": name, "entry_type": entry_type, "is_active": is_active}


# --------------------------------------------------------------------------
# Padrao: quem nunca configurou nada nao muda de comportamento
# --------------------------------------------------------------------------


async def test_empresa_sem_configuracao_devolve_o_padrao(client: AsyncClient, cenario: dict):
    resposta = await client.get(CONFIG, headers=cenario["admin"])

    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "note_mode": "hidden",
        "note_prompt": None,
        "label_mode": "hidden",
        "label_required": False,
        "labels": [],
    }


async def test_batida_sem_configuracao_continua_funcionando(client: AsyncClient, cenario: dict):
    """A funcionalidade nova nao pode custar nada a quem nao a quer."""
    resposta = await bater_ponto(client, cenario)

    assert resposta.status_code == 201, resposta.text
    entry = resposta.json()["entry"]
    assert entry["label"] is None
    assert entry["note"] is None


async def test_campo_enviado_sem_configuracao_que_o_peca_e_recusado(
    client: AsyncClient, cenario: dict
):
    """Aceitar em silencio esconderia app desatualizado ate alguem auditar."""
    resposta = await bater_ponto(client, cenario, note="qualquer coisa")

    assert resposta.status_code == 422, resposta.text


# --------------------------------------------------------------------------
# Observacao
# --------------------------------------------------------------------------


async def test_observacao_opcional_pode_vir_vazia(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, note_mode="optional")

    resposta = await bater_ponto(client, cenario)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["entry"]["note"] is None


async def test_observacao_opcional_e_gravada(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, note_mode="optional")

    resposta = await bater_ponto(client, cenario, note="  Cheguei atrasado, transito  ")

    assert resposta.status_code == 201, resposta.text
    # Espacos das pontas caem: sao do teclado, nao da declaracao.
    assert resposta.json()["entry"]["note"] == "Cheguei atrasado, transito"


async def test_observacao_obrigatoria_ausente_barra_a_batida(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, note_mode="required", note_prompt="Justifique o atraso")

    resposta = await bater_ponto(client, cenario)

    assert resposta.status_code == 422, resposta.text
    # A mensagem do RH e o que aparece na tela de quem esta batendo.
    assert resposta.json()["detail"] == "Justifique o atraso"


async def test_observacao_so_com_espacos_conta_como_ausente(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, note_mode="required")

    resposta = await bater_ponto(client, cenario, note="     ")

    assert resposta.status_code == 422, resposta.text


async def test_observacao_longa_demais_e_recusada(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, note_mode="optional")

    resposta = await bater_ponto(client, cenario, note="x" * 501)

    assert resposta.status_code == 422, resposta.text


# --------------------------------------------------------------------------
# Rotulo livre: descreve, mas nao decide
# --------------------------------------------------------------------------


async def test_rotulo_livre_e_gravado(client: AsyncClient, cenario: dict):
    await configurar(client, cenario, label_mode="free")

    resposta = await bater_ponto(client, cenario, label="Chegada ao hangar")

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["entry"]["label"] == "Chegada ao hangar"


async def test_rotulo_livre_nao_mexe_no_tipo(client: AsyncClient, cenario: dict):
    """O texto digitado nao pode alterar a contagem de horas."""
    await configurar(client, cenario, label_mode="free")

    resposta = await bater_ponto(client, cenario, label="saida para o almoco")

    assert resposta.status_code == 201, resposta.text
    # Primeira batida do dia: entrada, apesar do que o texto diz.
    assert resposta.json()["entry"]["entry_type"] == "in"


# --------------------------------------------------------------------------
# Rotulo por lista: e o unico modo que decide o tipo
# --------------------------------------------------------------------------


@pytest.fixture
async def com_lista(client: AsyncClient, cenario: dict) -> dict:
    resposta = await configurar(
        client,
        cenario,
        label_mode="list",
        label_required=True,
        labels=[
            rotulo("Entrada", "in"),
            rotulo("Inicio do almoco", "break_start"),
            rotulo("Volta do almoco", "break_end"),
            rotulo("Saida", "out"),
        ],
    )
    assert resposta.status_code == 200, resposta.text
    return cenario


async def test_rotulo_da_lista_define_o_tipo(client: AsyncClient, com_lista: dict):
    """O criterio de pronto desta feature.

    O funcionario escolhe "Inicio do almoco" sem saber o que e break_start; a
    traducao fica com quem entende de jornada, que e o RH.
    """
    resposta = await bater_ponto(client, com_lista, label="Inicio do almoco")

    assert resposta.status_code == 201, resposta.text
    entry = resposta.json()["entry"]
    assert entry["entry_type"] == "break_start"
    assert entry["label"] == "Inicio do almoco"


async def test_rotulo_da_lista_vence_a_deducao_automatica(client: AsyncClient, com_lista: dict):
    """Sem rotulo, a primeira batida do dia seria 'in'."""
    resposta = await bater_ponto(client, com_lista, label="Saida")

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["entry"]["entry_type"] == "out"


async def test_rotulo_fora_da_lista_e_recusado(client: AsyncClient, com_lista: dict):
    """Aceitar texto livre aqui deixaria inventar um tipo sem jornada."""
    resposta = await bater_ponto(client, com_lista, label="Fui tomar um cafe")

    assert resposta.status_code == 422, resposta.text


async def test_rotulo_obrigatorio_ausente_barra_a_batida(client: AsyncClient, com_lista: dict):
    resposta = await bater_ponto(client, com_lista)

    assert resposta.status_code == 422, resposta.text
    assert "tipo da batida" in resposta.json()["detail"]


async def test_rotulo_casa_sem_diferenciar_maiusculas(client: AsyncClient, com_lista: dict):
    resposta = await bater_ponto(client, com_lista, label="INICIO DO ALMOCO")

    assert resposta.status_code == 201, resposta.text
    # Grava com a grafia do cadastro, nao com a que veio na requisicao.
    assert resposta.json()["entry"]["label"] == "Inicio do almoco"


async def test_rotulo_desativado_nao_pode_ser_escolhido(client: AsyncClient, cenario: dict):
    await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Entrada", "in"), rotulo("Saida para campo", "out", is_active=False)],
    )

    resposta = await bater_ponto(client, cenario, label="Saida para campo")

    assert resposta.status_code == 422, resposta.text


# --------------------------------------------------------------------------
# O ponto e evidencia: mexer na config nao reescreve o passado
# --------------------------------------------------------------------------


async def test_renomear_rotulo_nao_altera_pontos_ja_batidos(client: AsyncClient, com_lista: dict):
    batida = await bater_ponto(client, com_lista, label="Inicio do almoco")
    assert batida.status_code == 201, batida.text
    entry_id = batida.json()["entry"]["id"]

    # O RH renomeia a opcao meses depois.
    await configurar(
        client,
        com_lista,
        label_mode="list",
        labels=[rotulo("Pausa para refeicao", "break_start")],
    )

    listagem = await client.get(
        "/api/v1/time-entries", headers=com_lista["admin"], params={"limit": 50}
    )
    assert listagem.status_code == 200, listagem.text
    gravado = next(e for e in listagem.json()["items"] if e["id"] == entry_id)

    assert gravado["label"] == "Inicio do almoco"
    assert gravado["entry_type"] == "break_start"


async def test_desligar_a_configuracao_nao_apaga_o_que_foi_declarado(
    client: AsyncClient, cenario: dict
):
    await configurar(client, cenario, note_mode="optional")
    batida = await bater_ponto(client, cenario, note="Justificativa registrada")
    assert batida.status_code == 201, batida.text
    entry_id = batida.json()["entry"]["id"]

    await configurar(client, cenario, note_mode="hidden")

    listagem = await client.get(
        "/api/v1/time-entries", headers=cenario["admin"], params={"limit": 50}
    )
    gravado = next(e for e in listagem.json()["items"] if e["id"] == entry_id)
    assert gravado["note"] == "Justificativa registrada"


# --------------------------------------------------------------------------
# Configuracoes que travariam a tela do funcionario
# --------------------------------------------------------------------------


async def test_lista_sem_opcao_ativa_e_recusada(client: AsyncClient, cenario: dict):
    """Deixaria o funcionario numa tela de escolha sem nada para escolher."""
    resposta = await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Entrada", "in", is_active=False)],
    )

    assert resposta.status_code == 422, resposta.text


async def test_exigir_rotulo_sem_exibi_lo_e_recusado(client: AsyncClient, cenario: dict):
    resposta = await configurar(client, cenario, label_mode="hidden", label_required=True)

    assert resposta.status_code == 422, resposta.text


async def test_rotulos_repetidos_sao_recusados(client: AsyncClient, cenario: dict):
    resposta = await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Entrada", "in"), rotulo("entrada", "out")],
    )

    assert resposta.status_code == 422, resposta.text


# --------------------------------------------------------------------------
# O que o app recebe
# --------------------------------------------------------------------------


async def test_app_recebe_so_o_necessario_para_desenhar_a_tela(
    client: AsyncClient, com_lista: dict
):
    resposta = await client.get(f"{CONFIG}/form", headers=com_lista["app"])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["label_mode"] == "list"
    assert corpo["label_required"] is True
    assert [r["name"] for r in corpo["labels"]] == [
        "Entrada",
        "Inicio do almoco",
        "Volta do almoco",
        "Saida",
    ]
    # Sem entry_type: quem traduz rotulo em jornada e o servidor.
    assert all("entry_type" not in r for r in corpo["labels"])


async def test_app_nao_ve_rotulo_desativado(client: AsyncClient, cenario: dict):
    await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Entrada", "in"), rotulo("Saida para campo", "out", is_active=False)],
    )

    resposta = await client.get(f"{CONFIG}/form", headers=cenario["app"])

    assert [r["name"] for r in resposta.json()["labels"]] == ["Entrada"]


async def test_rh_ve_rotulo_desativado(client: AsyncClient, cenario: dict):
    """A visao do painel e outra: sem os inativos, o RH nao consegue reativar."""
    await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Entrada", "in"), rotulo("Saida para campo", "out", is_active=False)],
    )

    resposta = await client.get(CONFIG, headers=cenario["admin"])

    nomes = [r["name"] for r in resposta.json()["labels"]]
    assert nomes == ["Entrada", "Saida para campo"]


async def test_ordem_dos_rotulos_e_a_que_o_rh_montou(client: AsyncClient, cenario: dict):
    await configurar(
        client,
        cenario,
        label_mode="list",
        labels=[rotulo("Saida", "out"), rotulo("Entrada", "in")],
    )

    resposta = await client.get(f"{CONFIG}/form", headers=cenario["app"])

    assert [r["name"] for r in resposta.json()["labels"]] == ["Saida", "Entrada"]


# --------------------------------------------------------------------------
# Isolamento e permissao
# --------------------------------------------------------------------------


async def test_configuracao_nao_vaza_entre_empresas(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await configurar(client, cenario, label_mode="list", labels=[rotulo("Entrada", "in")])

    outra = await create_tenant(db, slug="outra")
    await create_admin(db, outra, email="rh@outra.com")
    await db.commit()
    admin_outra = auth_header((await login_admin(client, outra, "rh@outra.com"))["tokens"])

    resposta = await client.get(CONFIG, headers=admin_outra)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["label_mode"] == "hidden"
    assert resposta.json()["labels"] == []


async def test_funcionario_nao_altera_a_configuracao(client: AsyncClient, cenario: dict):
    resposta = await client.put(
        CONFIG,
        headers=cenario["app"],
        json={"note_mode": "required", "label_mode": "hidden", "labels": []},
    )

    assert resposta.status_code in (401, 403), resposta.text
