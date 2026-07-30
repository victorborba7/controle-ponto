"""Decodificacao e guarda de imagens recebidas.

Primeira barreira antes de qualquer byte chegar ao modelo. Roda mesmo com a
engine stub: a entrada e um upload de fora, e validar upload nao e
responsabilidade do reconhecimento facial.
"""

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.facial.errors import ImageDecodeError, ImageTooLargeError

# Selfie de celular comprimida fica bem abaixo disto. O limite existe para
# cortar upload absurdo antes de gastar CPU decodificando.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Protecao contra "decompression bomb": um PNG de poucos KB pode declarar
# dimensoes gigantescas e estourar a memoria ao ser expandido.
MAX_PIXELS = 40_000_000

MIN_DIMENSION = 64

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    format: str

    @property
    def pixels(self) -> int:
        return self.width * self.height


def inspect_image(data: bytes) -> ImageInfo:
    """Valida o upload e devolve as dimensoes, sem decodificar os pixels.

    `Image.open` le so o cabecalho, entao dimensao e formato saem baratos e um
    arquivo malicioso e barrado antes de virar bitmap na memoria.
    """
    if not data:
        raise ImageDecodeError("Imagem vazia")

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(
            f"Imagem com {len(data)} bytes excede o limite de {MAX_IMAGE_BYTES}"
        )

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format or ""
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError("Nao foi possivel ler a imagem") from exc

    if image_format not in ALLOWED_FORMATS:
        raise ImageDecodeError(
            f"Formato {image_format or 'desconhecido'} nao suportado. "
            f"Use {', '.join(sorted(ALLOWED_FORMATS))}."
        )

    if width * height > MAX_PIXELS:
        raise ImageTooLargeError(f"Imagem com {width}x{height} pixels excede o limite")

    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageDecodeError(
            f"Imagem {width}x{height} e pequena demais (minimo {MIN_DIMENSION}px por lado)"
        )

    return ImageInfo(width=width, height=height, format=image_format)


def decode_rgb(data: bytes) -> Image.Image:
    """Decodifica para RGB, ja validado.

    Converte sempre para RGB porque a entrada pode vir em RGBA (PNG com
    transparencia), escala de cinza ou com perfil de cor exotico, e o modelo
    espera tres canais.
    """
    inspect_image(data)
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError("Nao foi possivel decodificar a imagem") from exc
