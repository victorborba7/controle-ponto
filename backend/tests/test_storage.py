"""Armazenamento de imagens: chaves opacas e confinamento no diretorio."""

import uuid

import pytest

from app.services.storage import (
    InvalidKeyError,
    LocalStorage,
    ObjectNotFoundError,
    build_key,
    validate_key,
)


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path)


# --------------------------------------------------------------------------
# Formato das chaves
# --------------------------------------------------------------------------


def test_chave_gerada_e_opaca():
    """Nada na chave revela quem esta na foto."""
    chave = build_key("faces", "JPEG")

    prefixo, arquivo = chave.split("/")
    identificador, extensao = arquivo.split(".")

    assert prefixo == "faces"
    assert extensao == "jpg"
    uuid.UUID(identificador)  # levanta se nao for UUID


def test_chaves_nao_se_repetem():
    assert build_key("faces", "PNG") != build_key("faces", "PNG")


def test_extensao_segue_o_formato():
    assert build_key("faces", "PNG").endswith(".png")
    assert build_key("faces", "WEBP").endswith(".webp")
    assert build_key("faces", "FORMATO-ESTRANHO").endswith(".bin")


@pytest.mark.parametrize(
    "chave",
    [
        "../etc/passwd",
        "faces/../../segredo.png",
        "faces/nome-do-funcionario.png",
        "/absoluto/arquivo.png",
        "sem-barra.png",
        "faces/nao-e-uuid.png",
        "",
    ],
)
def test_chaves_fora_do_formato_sao_rejeitadas(chave: str):
    with pytest.raises(InvalidKeyError):
        validate_key(chave)


# --------------------------------------------------------------------------
# Ciclo de vida do objeto
# --------------------------------------------------------------------------


async def test_grava_e_le(storage: LocalStorage):
    conteudo = b"bytes-da-imagem"
    chave = await storage.save(conteudo, prefix="faces", image_format="PNG")

    assert await storage.load(chave) == conteudo
    assert await storage.exists(chave)


async def test_ler_objeto_inexistente(storage: LocalStorage):
    chave = build_key("faces", "PNG")
    with pytest.raises(ObjectNotFoundError):
        await storage.load(chave)


async def test_exists_e_falso_para_chave_desconhecida(storage: LocalStorage):
    assert await storage.exists(build_key("faces", "PNG")) is False


async def test_remove(storage: LocalStorage):
    chave = await storage.save(b"dados", prefix="selfies", image_format="JPEG")
    await storage.delete(chave)
    assert await storage.exists(chave) is False


async def test_remover_duas_vezes_nao_falha(storage: LocalStorage):
    """O expurgo da politica de retencao pode reprocessar registro ja limpo."""
    chave = await storage.save(b"dados", prefix="selfies", image_format="JPEG")
    await storage.delete(chave)
    await storage.delete(chave)


async def test_prefixos_ficam_em_pastas_separadas(storage: LocalStorage, tmp_path):
    await storage.save(b"a", prefix="faces", image_format="PNG")
    await storage.save(b"b", prefix="selfies", image_format="PNG")

    assert (tmp_path / "faces").is_dir()
    assert (tmp_path / "selfies").is_dir()


async def test_nao_le_arquivo_fora_do_storage(storage: LocalStorage, tmp_path):
    """Traversal barrado mesmo com um arquivo real do outro lado."""
    alvo = tmp_path.parent / "segredo.txt"
    alvo.write_bytes(b"conteudo sensivel")

    with pytest.raises(InvalidKeyError):
        await storage.load("faces/../../segredo.txt")
