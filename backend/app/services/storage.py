"""Armazenamento de imagens.

Abstraido desde o MVP porque o destino muda na fase 2 (disco local -> S3) e as
chaves gravadas em `face_templates.source_image_key` e
`time_entries.selfie_image_key` precisam continuar validas na migracao.

**Chaves sao opacas**: um UUID, nunca o nome do arquivo enviado nem algo
derivado do funcionario. Chave previsivel viraria enumeracao de fotos de
rosto, e chave derivada de nome vazaria quem esta na imagem para quem so
enxerga a chave.

Criptografia em repouso entra na Etapa 11 — aqui fica so o formato de acesso.
"""

import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import anyio

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
        await anyio.to_thread.run_sync(path.parent.mkdir, True, True)
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
