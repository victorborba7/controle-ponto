"""Normalizacao dos identificadores de localizacao.

O ponto de toda esta camada e um so: **o identificador cadastrado precisa ser
byte a byte igual ao que o aparelho vai reportar.** Um beacon gravado como
`EDD1EBEAC04E5DEFA017` e reportado como `edd1ebeac04e5defa017` simplesmente
nunca casa — e a falha e silenciosa, porque nada erra, o beacon so nunca e
reconhecido. Normalizar na entrada e mais barato que depurar isso no hangar.

Regra da casa: hexadecimal sempre em minusculas e sem separadores; BSSID em
minusculas com dois-pontos; UUID na forma canonica.
"""

import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Eddystone-UID: 10 bytes de namespace + 6 bytes de instance.
EDDYSTONE_NAMESPACE_BYTES = 10
EDDYSTONE_INSTANCE_BYTES = 6

# RSSI e negativo: 0 dBm seria o transmissor encostado na antena. Fora desta
# faixa e erro de digitacao, nao configuracao agressiva.
MIN_RSSI_LIMIT = -100
MAX_RSSI_LIMIT = -30

_NON_HEX = re.compile(r"[^0-9a-fA-F]")


class IdentifierError(ValueError):
    """Identificador fora do formato esperado."""


def normalize_hex(value: str, *, expected_bytes: int, label: str) -> str:
    """Hex em minusculas, sem separadores, com tamanho exato.

    Aceita as varias formas em que um fabricante imprime o valor na etiqueta
    (com espacos, com hifens, em maiusculas) e converte para uma so.
    """
    cleaned = _NON_HEX.sub("", value).lower()
    expected_chars = expected_bytes * 2

    if len(cleaned) != expected_chars:
        raise IdentifierError(
            f"{label} deve ter {expected_bytes} bytes ({expected_chars} digitos "
            f"hexadecimais); recebido {len(cleaned)}"
        )
    return cleaned


def normalize_eddystone_namespace(value: str) -> str:
    return normalize_hex(value, expected_bytes=EDDYSTONE_NAMESPACE_BYTES, label="Namespace")


def normalize_eddystone_instance(value: str) -> str:
    return normalize_hex(value, expected_bytes=EDDYSTONE_INSTANCE_BYTES, label="Instance")


def normalize_ibeacon_uuid(value: str) -> str:
    """UUID na forma canonica em minusculas.

    Passa pelo `uuid.UUID` de proposito: ele aceita as varias grafias (com ou
    sem hifens, entre chaves) e devolve sempre a mesma.
    """
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise IdentifierError(f"UUID de iBeacon invalido: {value!r}") from exc


def normalize_bssid(value: str) -> str:
    """MAC do ponto de acesso em `aa:bb:cc:dd:ee:ff`.

    O Android reporta com dois-pontos em minusculas, mas etiqueta de
    equipamento costuma vir com hifen ou em maiusculas — todas convergem aqui.
    """
    cleaned = _NON_HEX.sub("", value).lower()
    if len(cleaned) != 12:
        raise IdentifierError(
            f"BSSID deve ter 6 bytes (12 digitos hexadecimais); recebido {len(cleaned)}"
        )
    return ":".join(cleaned[index : index + 2] for index in range(0, 12, 2))


def validate_rssi(value: int) -> int:
    """Limiar de proximidade, em dBm.

    Referencia pratica: -60 e quase encostado, -75 sao poucos metros, -90 e o
    beacon do outro lado do galpao. Cadastrar um limiar frouxo demais faz
    presenca ser confirmada de longe, que e justamente o que a cadeia de
    localizacao deveria impedir.
    """
    if not MIN_RSSI_LIMIT <= value <= MAX_RSSI_LIMIT:
        raise IdentifierError(
            f"RSSI minimo deve ficar entre {MIN_RSSI_LIMIT} e {MAX_RSSI_LIMIT} dBm "
            f"(recebido {value}). Valores positivos nao existem em medicao real."
        )
    return value


def validate_timezone(value: str) -> str:
    """Fuso valido pela base IANA.

    Guardado por site, e nao global: uma empresa com unidade em Manaus e outra
    em Sao Paulo fecha jornada em horarios diferentes.
    """
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise IdentifierError(
            f"Fuso horario desconhecido: {value!r}. Use um nome IANA, "
            "como America/Sao_Paulo."
        ) from exc
    return value
