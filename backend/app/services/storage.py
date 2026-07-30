"""Armazenamento de imagens.

Abstraido desde o MVP porque o destino muda na fase 2 (disco local -> S3) e as
chaves gravadas em `face_templates.source_image_key` e
`time_entries.selfie_image_key` precisam continuar validas na migracao.

**Chaves sao opacas**: um UUID, nunca o nome do arquivo enviado nem algo
derivado do funcionario. Chave previsivel viraria enumeracao de fotos de
rosto, e chave derivada de nome vazaria quem esta na imagem para quem so
enxerga a chave.

**Conteudo criptografado**: `EncryptedStorage` envolve qualquer backend e
cifra antes de gravar. Imagem de rosto e dado biometrico — dado pessoal
sensivel pela LGPD —, entao gravar em claro nao e aceitavel nem em disco
local de desenvolvimento.
"""

import base64
import os
import re
import uuid
from abc import ABC, abstractmethod
from functools import partial
from pathlib import Path

import anyio
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Formato da chave: <prefixo>/<uuid>.<extensao>
_KEY_PATTERN = re.compile(r"^[a-z0-9_-]{1,40}/[0-9a-f-]{36}\.[a-z0-9]{1,8}$")

_EXTENSION_BY_FORMAT = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}


class StorageError(Exception):
    pass


class ObjectNotFoundError(StorageError):
    pass


class DecryptionError(StorageError):
    """Objeto nao pode ser decifrado: chave trocada ou conteudo adulterado."""


class InvalidKeyError(StorageError):
    """Chave fora do formato esperado.

    Barrar aqui e o que impede que uma chave vinda do banco (ou adulterada)
    contenha `../` e alcance arquivo fora do diretorio de armazenamento.
    """


def build_key(prefix: str, image_format: str) -> str:
    """Monta uma chave opaca nova."""
    extension = _EXTENSION_BY_FORMAT.get(image_format.upper(), "bin")
    key = f"{prefix}/{uuid.uuid4()}.{extension}"
    validate_key(key)
    return key


def validate_key(key: str) -> str:
    if not _KEY_PATTERN.match(key):
        raise InvalidKeyError(f"Chave invalida: {key!r}")
    return key


class Storage(ABC):
    """Contrato de armazenamento de objetos."""

    @abstractmethod
    async def save(self, data: bytes, *, prefix: str, image_format: str) -> str:
        """Grava e devolve a chave opaca gerada."""

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """Le o objeto. Levanta ObjectNotFoundError se nao existir."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove o objeto. Silencioso se ja nao existir (idempotente)."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        ...


class LocalStorage(Storage):
    """Grava em disco. Suficiente para o MVP de uma empresa so.

    Na fase 2 vira S3Storage: mesma interface, mesmas chaves, e o unico ajuste
    e a configuracao.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path).resolve()

    def _path_for(self, key: str) -> Path:
        validate_key(key)
        path = (self._base / key).resolve()
        # Cinto e suspensorio: mesmo com a chave validada, confirma que o
        # caminho resolvido continua dentro da base.
        if not path.is_relative_to(self._base):
            raise InvalidKeyError(f"Chave aponta para fora do storage: {key!r}")
        return path

    async def save(self, data: bytes, *, prefix: str, image_format: str) -> str:
        key = build_key(prefix, image_format)
        path = self._path_for(key)
        # partial, e nao argumentos posicionais: `run_sync` nao repassa kwargs,
        # e a ordem posicional de mkdir e (mode, parents, exist_ok) — passar
        # (True, True) definiria mode=1 e deixaria exist_ok=False, quebrando a
        # segunda gravacao no mesmo prefixo.
        await anyio.to_thread.run_sync(
            partial(path.parent.mkdir, parents=True, exist_ok=True)
        )
        await anyio.Path(path).write_bytes(data)
        return key

    async def load(self, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return await anyio.Path(path).read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Objeto nao encontrado: {key}") from exc

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        try:
            await anyio.Path(path).unlink()
        except FileNotFoundError:
            # Idempotente: o expurgo da politica de retencao (Etapa 11) pode
            # reprocessar um registro cuja imagem ja saiu.
            pass

    async def exists(self, key: str) -> bool:
        return await anyio.Path(self._path_for(key)).exists()


# AES-GCM: cifra e autentica ao mesmo tempo, entao conteudo adulterado falha
# na leitura em vez de devolver lixo. Nonce de 12 bytes e o tamanho recomendado.
_NONCE_BYTES = 12
_KEY_BYTES = 32


class EncryptedStorage(Storage):
    """Cifra o conteudo antes de entregar ao backend real.

    Envolve qualquer Storage, entao a mesma protecao vale para disco local hoje
    e para S3 na fase 2. O backend interno nunca ve bytes em claro.

    A chave nao rotaciona sozinha: trocar a chave torna ilegivel tudo que ja
    foi gravado. Rotacao de verdade exigiria versionar a chave no objeto, o que
    fica para quando houver motivo real de rotacionar.
    """

    def __init__(self, inner: Storage, key_base64: str) -> None:
        try:
            key = base64.b64decode(key_base64, validate=True)
        except Exception as exc:
            raise StorageError("STORAGE_ENCRYPTION_KEY nao e base64 valido") from exc

        if len(key) != _KEY_BYTES:
            raise StorageError(
                f"STORAGE_ENCRYPTION_KEY precisa ter {_KEY_BYTES} bytes "
                f"(recebidos {len(key)}). Gere com: "
                'python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"'
            )

        self._inner = inner
        self._aes = AESGCM(key)

    async def save(self, data: bytes, *, prefix: str, image_format: str) -> str:
        # Nonce novo a cada objeto: reutilizar nonce com a mesma chave quebra a
        # garantia do GCM por completo.
        nonce = os.urandom(_NONCE_BYTES)
        sealed = nonce + self._aes.encrypt(nonce, data, None)
        return await self._inner.save(sealed, prefix=prefix, image_format=image_format)

    async def load(self, key: str) -> bytes:
        sealed = await self._inner.load(key)
        if len(sealed) <= _NONCE_BYTES:
            raise DecryptionError(f"Objeto {key} esta truncado")

        nonce, ciphertext = sealed[:_NONCE_BYTES], sealed[_NONCE_BYTES:]
        try:
            return self._aes.decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise DecryptionError(
                f"Objeto {key} nao pode ser decifrado: chave trocada ou conteudo alterado"
            ) from exc

    async def delete(self, key: str) -> None:
        await self._inner.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._inner.exists(key)


def build_storage(base_path: str, encryption_key: str) -> Storage:
    """Storage da aplicacao: disco local, com o conteudo cifrado."""
    return EncryptedStorage(LocalStorage(base_path), encryption_key)
