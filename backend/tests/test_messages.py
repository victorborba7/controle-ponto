"""Testes do catalogo de mensagens.

O que importa aqui nao e o texto — texto muda. E que nenhum idioma fique com
buraco, que nenhuma frase seja montada por concatenacao, e que a negociacao
de idioma nao invente resposta quando o cabecalho vem estranho.
"""

import pytest

from app.core.messages import (
    CATALOGO,
    IDIOMA_PADRAO,
    Msg,
    idiomas_disponiveis,
    negociar_idioma,
    traduzir,
    verificar_catalogo,
)


def test_todo_idioma_tem_todas_as_chaves():
    """Chave faltando apareceria em ingles no meio de uma tela em portugues."""
    faltando = verificar_catalogo()
    assert faltando == {}, f"chaves sem traducao: {faltando}"


def test_nenhum_idioma_tem_chave_a_mais():
    """Chave orfa e mensagem que ninguem exibe — restou de uma remocao."""
    validas = {m.value for m in Msg}
    for idioma, tabela in CATALOGO.items():
        orfas = {k.value for k in tabela} - validas
        assert not orfas, f"{idioma} tem chaves inexistentes: {orfas}"


def test_ingles_e_o_padrao():
    assert IDIOMA_PADRAO == "en"
    assert IDIOMA_PADRAO in idiomas_disponiveis()


@pytest.mark.parametrize("idioma", sorted(CATALOGO))
def test_nenhuma_mensagem_vazia_ou_com_sobra_de_espaco(idioma: str):
    """Concatenacao mal fechada costuma virar espaco duplo ou sobra na ponta."""
    for chave, texto in CATALOGO[idioma].items():
        assert texto.strip() == texto, f"{idioma}/{chave.value} tem espaco na ponta"
        assert "  " not in texto, f"{idioma}/{chave.value} tem espaco duplo"
        assert texto, f"{idioma}/{chave.value} esta vazia"


@pytest.mark.parametrize("idioma", sorted(CATALOGO))
def test_parametros_sao_os_mesmos_em_todos_os_idiomas(idioma: str):
    """Traducao que esquece um `{limit}` gera frase truncada, nao erro.

    E traducao que inventa um placebo a mais estoura `KeyError` no `format`,
    o que e pior: vira 500 no lugar da mensagem de validacao.
    """
    import string

    def campos(texto: str) -> set[str]:
        return {nome for _, nome, _, _ in string.Formatter().parse(texto) if nome is not None}

    for chave, texto in CATALOGO[idioma].items():
        esperado = campos(CATALOGO[IDIOMA_PADRAO][chave])
        assert campos(texto) == esperado, (
            f"{idioma}/{chave.value} usa {campos(texto)}, " f"o padrao usa {esperado}"
        )


def test_traduzir_aplica_parametros():
    texto = traduzir(Msg.OBSERVACAO_LONGA, "en", limit=500)
    assert "500" in texto
    assert "{" not in texto


def test_traduzir_cai_no_padrao_em_idioma_desconhecido():
    """Frase em ingles inesperada e ruim; 500 no lugar de 404 e pior."""
    assert traduzir(Msg.LOCAL_NAO_ENCONTRADO, "de") == traduzir(
        Msg.LOCAL_NAO_ENCONTRADO, IDIOMA_PADRAO
    )


@pytest.mark.parametrize(
    ("cabecalho", "esperado"),
    [
        (None, "en"),
        ("", "en"),
        ("pt-BR", "pt"),
        ("pt-BR,pt;q=0.9,en;q=0.8", "pt"),
        ("en-US,en;q=0.9", "en"),
        # Peso decide, nao a ordem de escrita.
        ("pt;q=0.2,en;q=0.9", "en"),
        ("en;q=0.2,pt;q=0.9", "pt"),
        # Idioma que nao temos e ignorado, o proximo conhecido vence.
        ("de-DE,fr;q=0.9,pt;q=0.5", "pt"),
        ("de-DE,fr;q=0.9", "en"),
        # `*` nao deve ganhar do padrao.
        ("*", "en"),
        # Cabecalho quebrado nao pode derrubar a requisicao.
        ("pt;q=abc", "pt"),
        (",,,", "en"),
        (";q=0.9", "en"),
    ],
)
def test_negociacao_de_idioma(cabecalho: str | None, esperado: str):
    assert negociar_idioma(cabecalho) == esperado


def test_empate_de_peso_respeita_a_ordem_do_cabecalho():
    """A especificacao desempata pela ordem de escrita."""
    assert negociar_idioma("pt,en") == "pt"
    assert negociar_idioma("en,pt") == "en"


# --------------------------------------------------------------------------
# De ponta a ponta: o cabecalho do cliente chega mesmo na resposta
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_erro_sai_no_idioma_pedido(client):
    """Sem cabecalho, ingles; com `Accept-Language: pt-BR`, portugues.

    Vale a pena testar pela borda HTTP e nao so pela funcao: a negociacao so
    serve para alguma coisa se a dependencia estiver ligada no endpoint, e
    esquecer de liga-la nao quebra nenhum teste de unidade.
    """
    sem_cabecalho = await client.get("/api/v1/employees")
    assert sem_cabecalho.status_code == 401
    assert sem_cabecalho.json()["detail"] == traduzir(Msg.SESSAO_EXPIRADA, "en")

    em_portugues = await client.get(
        "/api/v1/employees", headers={"Accept-Language": "pt-BR,pt;q=0.9"}
    )
    assert em_portugues.status_code == 401
    assert em_portugues.json()["detail"] == traduzir(Msg.SESSAO_EXPIRADA, "pt")

    # Idioma que nao temos nao pode virar erro nem texto vazio.
    em_alemao = await client.get("/api/v1/employees", headers={"Accept-Language": "de-DE"})
    assert em_alemao.status_code == 401
    assert em_alemao.json()["detail"] == traduzir(Msg.SESSAO_EXPIRADA, "en")
